"""Voice orchestration engine: telephony -> STT -> LLM -> TTS pipeline with retry, fallback and handover.
It only depends on provider interfaces, so real providers drop in via the registry (providers/__init__.py).
Call lifecycle: start_call() -> handle_utterance()* -> end_call().   simulate_call() runs all three."""
import math
import wave
from datetime import datetime, timedelta
from pathlib import Path

from flask import current_app

from .. import db
from . import providers
from .providers import ProviderError
from .providers.mock import DEFAULT_SCRIPTS, sentiment, t

FMT = "%Y-%m-%d %H:%M:%S"
MAX_TURNS = 40


def _retry(fn, tries=2):
    last = None
    for attempt in range(tries):
        try:
            return fn(attempt)
        except ProviderError as e:
            last = e
    raise last


def _add_turn(call, speaker, text, intent=None, confidence=None, latency_ms=0, duration_ms=0):
    row = db.query("SELECT COALESCE(MAX(seq),0) AS s, COALESCE(SUM(duration_ms),0) AS d FROM call_turns WHERE call_id=?",
                   (call["id"],), one=True)
    ts = (datetime.strptime(call["started_at"], FMT) + timedelta(milliseconds=row["d"])).strftime(FMT)
    db.execute("INSERT INTO call_turns(call_id,seq,speaker,text,intent,confidence,latency_ms,duration_ms,ts) VALUES (?,?,?,?,?,?,?,?,?)",
               (call["id"], row["s"] + 1, speaker, text, intent, confidence, latency_ms, duration_ms, ts))


def _call(call_id):
    return db.query("SELECT * FROM calls WHERE id=?", (call_id,), one=True)


def _agent_ctx(call):
    agent = db.query("SELECT * FROM agents WHERE id=?", (call["agent_id"],), one=True)
    company = db.query("SELECT * FROM companies WHERE id=?", (call["company_id"],), one=True)
    kb = db.query("SELECT title,content FROM knowledge_docs WHERE agent_id=?", (agent["id"],))
    return agent, company, kb


def _speak(call, agent, text, intent=None, latency=0):
    tts = providers.get("tts", agent["tts_provider"])
    try:
        r = _retry(lambda a: tts.synthesize(text, call["language"], agent["voice"], {"attempt": a}))
    except ProviderError:
        r = {"duration_ms": 1000, "latency_ms": 0}
    _add_turn(call, "agent", text, intent=intent, latency_ms=latency + r["latency_ms"], duration_ms=r["duration_ms"] + latency)


def start_call(agent, direction, party_number, scenario="normal", is_test=False, started_at=None):
    """Create the call, ask telephony to connect it, speak the greeting. Returns call id."""
    company = db.query("SELECT * FROM companies WHERE id=?", (agent["company_id"],), one=True)
    started_at = started_at or db.now()
    did = agent["phone_number"] or "+91 00000 00000"
    frm, to = (party_number, did) if direction == "inbound" else (did, party_number)
    tel = providers.get("telephony", agent["telephony_provider"])
    res = tel.place_call(frm, to, direction, {"scenario": scenario, "seed": started_at})
    connected = res["status"] == "connected"
    cid = db.execute(
        "INSERT INTO calls(company_id,agent_id,agent_version,direction,from_number,to_number,language,status,scenario,is_test,provider_sid,started_at,ended_at,summary)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (agent["company_id"], agent["id"], agent["current_version"], direction, frm, to, agent["language"],
         "in_progress" if connected else res["status"], scenario, int(is_test), res["sid"], started_at,
         None if connected else started_at, "" if connected else f"Call not connected: {res['status']}."))
    if connected:
        call = _call(cid)
        greeting = agent["greeting"] or t("greeting", agent["language"], company=company["name"])
        _speak(call, agent, greeting, intent="greeting")
    return cid


def handle_utterance(call_id, text):
    call = _call(call_id)
    if not call or call["status"] != "in_progress":
        raise ProviderError("Call is not in progress")
    agent, company, kb = _agent_ctx(call)
    lang, sc = call["language"], call["scenario"]
    n_turns = db.query("SELECT COUNT(*) c FROM call_turns WHERE call_id=?", (call_id,), one=True)["c"]
    if n_turns >= MAX_TURNS:
        return end_call(call_id)

    def fallback_to_human(heard):
        db.execute("UPDATE calls SET errors=errors+1 WHERE id=?", (call_id,))
        _add_turn(call, "caller", heard, duration_ms=len(text) * 65)
        _speak(call, agent, t("error", lang), intent="error")
        return end_call(call_id, transfer=True)

    # 1) speech-to-text (retry once)
    stt = providers.get("stt", agent["stt_provider"])
    try:
        heard = _retry(lambda a: stt.transcribe(text, lang, {"scenario": sc, "attempt": a}))
    except ProviderError:
        return fallback_to_human("[inaudible]")
    # 2) LLM (retry once)
    llm = providers.get("llm", agent["llm_provider"])
    history = [r["text"] for r in db.query("SELECT text FROM call_turns WHERE call_id=? ORDER BY seq", (call_id,))]
    try:
        out = _retry(lambda a: llm.respond({"language": lang, "company": company["name"], "agent": agent, "history": history,
                                            "user_text": heard["text"], "knowledge": kb, "scenario": sc, "attempt": a}))
    except ProviderError:
        return fallback_to_human(heard["text"])
    _add_turn(call, "caller", heard["text"], intent=out["intent"], confidence=heard["confidence"],
              latency_ms=heard["latency_ms"], duration_ms=len(heard["text"]) * 65 + heard["latency_ms"])
    # 3) text-to-speech
    _speak(call, agent, out["text"], intent=out["intent"], latency=out["latency_ms"])
    if out["handover"]:
        return end_call(call_id, transfer=True)
    if out["intent"] == "bye":
        return end_call(call_id)
    return _call(call_id)


def _build_recording(call_id):
    """Placeholder-tone WAV built from the transcript timeline (NOT real speech)."""
    rate, frames = 8000, bytearray()
    for r in db.query("SELECT speaker,duration_ms FROM call_turns WHERE call_id=? ORDER BY seq", (call_id,)):
        secs = min(r["duration_ms"] / 1000, 1.0 if r["speaker"] == "agent" else 0.5)
        freq, amp = (440, 9000) if r["speaker"] == "agent" else (330, 4500)
        n = int(rate * secs)
        for i in range(n):
            env = min(1, i / 200, (n - i) / 200)
            v = int(amp * env * math.sin(2 * math.pi * freq * i / rate))
            frames += v.to_bytes(2, "little", signed=True)
        frames += bytes(2 * int(rate * 0.15))
    name = f"call_{call_id}.wav"
    path = Path(current_app.config["RECORDINGS_DIR"]) / name
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        w.writeframes(bytes(frames))
    return name


def end_call(call_id, transfer=False):
    call = _call(call_id)
    if call["status"] != "in_progress":
        return call
    agent, company, _ = _agent_ctx(call)
    turns = db.query("SELECT * FROM call_turns WHERE call_id=? ORDER BY seq", (call_id,))
    duration = max(1, round(sum(r["duration_ms"] for r in turns) / 1000))
    target = None
    if transfer:
        tel = providers.get("telephony", agent["telephony_provider"])
        target = agent["handover_number"] or "unconfigured"
        tel.transfer(call["provider_sid"], target)
    status = "transferred" if transfer else "completed"
    llm = providers.get("llm", agent["llm_provider"])
    try:
        summary = llm.summarize({"intents": [r["intent"] for r in turns if r["speaker"] == "caller" and r["intent"]],
                                 "status": status, "direction": call["direction"], "language": call["language"], "turns": len(turns)})
    except ProviderError:
        summary = "Summary unavailable (provider error)."
    ended = (datetime.strptime(call["started_at"], FMT) + timedelta(seconds=duration)).strftime(FMT)
    db.execute("UPDATE calls SET status=?,ended_at=?,duration_sec=?,billable_minutes=?,summary=?,sentiment=?,handover=?,handover_target=?,recording_file=? WHERE id=?",
               (status, ended, duration, math.ceil(duration / 60), summary, sentiment([r["text"] for r in turns if r["speaker"] == "caller"]),
                int(transfer), target, _build_recording(call_id), call_id))
    return _call(call_id)


def simulate_call(agent, direction="inbound", party_number="+91 98250 00000", scenario="normal",
                  utterances=None, is_test=False, started_at=None):
    cid = start_call(agent, direction, party_number, scenario, is_test, started_at)
    for line in (utterances or DEFAULT_SCRIPTS.get(agent["language"], DEFAULT_SCRIPTS["en"])):
        if _call(cid)["status"] != "in_progress":
            break
        handle_utterance(cid, str(line)[:500])
    if _call(cid)["status"] == "in_progress":
        end_call(cid)
    return _call(cid)
