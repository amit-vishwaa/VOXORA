"""SIMULATED providers. No AI, no speech, no phone network: deterministic rule-based behaviour used for
local development and automated tests. Scenarios inject failures:
  normal | no_answer | busy | network_failure | stt_flaky | stt_failure | llm_flaky | llm_timeout | handover
"""
import re
import zlib

from .base import ProviderError, STTProvider, LLMProvider, TTSProvider, TelephonyProvider

SCENARIOS = ["normal", "no_answer", "busy", "network_failure", "stt_flaky", "stt_failure",
             "llm_flaky", "llm_timeout", "handover"]


def _jitter(text, base, spread=80):
    return base + zlib.crc32(text.encode("utf-8")) % spread


# ----------------------------------------------------------------------------- language data
KEYWORDS = {
    "human": ["human", "real person", "representative", "operator", "इंसान", "व्यक्ति से", "प्रतिनिधि", "માણસ", "વ્યક્તિ સાથે", "પ્રતિનિધિ"],
    "bye": ["thank", "bye", "धन्यवाद", "अलविदा", "આભાર", "આવજો"],
    "price": ["price", "cost", "fee", "charges", "rate", "कीमत", "दाम", "फीस", "शुल्क", "કિંમત", "ભાવ", "ફી", "ચાર્જ"],
    "hours": ["hour", "timing", "open", "close", "समय", "खुले", "बजे", "સમય", "ખુલ્લ", "વાગ્યે"],
    "booking": ["book", "appointment", "schedule", "visit", "demo", "बुक", "अपॉइंटमेंट", "विज़िट", "બુક", "એપોઇન્ટમેન્ટ", "મુલાકાત"],
    "greet": ["hello", "hi", "hey", "नमस्ते", "हैलो", "નમસ્તે", "હેલો"],
}
INTENT_ORDER = ["human", "bye", "price", "hours", "booking", "greet"]

NEG = ["angry", "bad", "terrible", "worst", "not happy", "गुस्सा", "खराब", "ગુસ્સો", "ખરાબ"]
POS = ["thank", "great", "good", "perfect", "धन्यवाद", "बढ़िया", "આભાર", "સરસ"]

T = {
    "greeting": {"en": "Hello! You have reached {company}. How can I help you today?",
                 "hi": "नमस्ते! आपने {company} को कॉल किया है। मैं आपकी कैसे मदद कर सकता हूँ?",
                 "gu": "નમસ્તે! તમે {company} ને કૉલ કર્યો છે. હું તમારી શું મદદ કરી શકું?"},
    "hours": {"en": "Our standard working hours are 10 AM to 7 PM, Monday to Saturday.",
              "hi": "हमारे काम के घंटे सोमवार से शनिवार, सुबह 10 बजे से शाम 7 बजे तक हैं।",
              "gu": "અમારા કામના કલાકો સોમવારથી શનિવાર, સવારે 10 થી સાંજે 7 વાગ્યા સુધી છે."},
    "price": {"en": "I can share pricing details. Which service are you interested in?",
              "hi": "मैं कीमत की जानकारी दे सकता हूँ। आप किस सेवा के बारे में जानना चाहते हैं?",
              "gu": "હું કિંમતની માહિતી આપી શકું છું. તમે કઈ સેવા વિશે જાણવા માંગો છો?"},
    "booking": {"en": "Sure, I can help you book that. Please tell me your preferred date and time.",
                "hi": "ज़रूर, मैं बुकिंग में मदद कर सकता हूँ। कृपया अपनी पसंदीदा तारीख और समय बताइए।",
                "gu": "ચોક્કસ, હું બુકિંગમાં મદદ કરી શકું છું. કૃપા કરીને તમારી પસંદગીની તારીખ અને સમય જણાવો."},
    "human": {"en": "Of course, let me transfer you to a team member.",
              "hi": "ज़रूर, मैं आपको हमारी टीम के सदस्य से जोड़ता हूँ।",
              "gu": "ચોક્કસ, હું તમને અમારી ટીમના સભ્ય સાથે જોડું છું."},
    "bye": {"en": "Thank you for calling {company}. Have a great day!",
            "hi": "{company} को कॉल करने के लिए धन्यवाद। आपका दिन शुभ हो!",
            "gu": "{company} ને કૉલ કરવા બદલ આભાર. તમારો દિવસ શુભ રહે!"},
    "fallback": {"en": "I'm sorry, I didn't quite get that. Could you please rephrase?",
                 "hi": "क्षमा करें, मैं समझ नहीं पाया। क्या आप दोबारा बता सकते हैं?",
                 "gu": "માફ કરશો, હું સમજી શક્યો નહીં. શું તમે ફરીથી કહી શકશો?"},
    "error": {"en": "I'm having technical difficulty. Let me connect you to a team member.",
              "hi": "मुझे तकनीकी समस्या हो रही है। मैं आपको हमारी टीम से जोड़ता हूँ।",
              "gu": "મને તકનીકી સમસ્યા આવી રહી છે. હું તમને અમારી ટીમ સાથે જોડું છું."},
}
STOP = {"the", "and", "you", "for", "are", "what", "your", "can", "how", "with", "this", "that", "have", "tell", "about", "please"}

DEFAULT_SCRIPTS = {
    "en": ["Hello", "What are your timings?", "What is the price?", "I want to book an appointment", "Thank you, bye"],
    "hi": ["नमस्ते", "आपके खुलने का समय क्या है?", "फीस कितनी है?", "मुझे अपॉइंटमेंट बुक करना है", "धन्यवाद"],
    "gu": ["નમસ્તે", "તમારો સમય શું છે?", "ફી કેટલી છે?", "મારે એપોઇન્ટમેન્ટ બુક કરવી છે", "આભાર"],
}


def t(key, lang, **kw):
    return T[key].get(lang, T[key]["en"]).format(**kw)


def detect_intent(text):
    low = text.lower()
    for intent in INTENT_ORDER:
        for kw in KEYWORDS[intent]:
            if kw.isascii():
                if re.search(r"\b" + re.escape(kw), low):
                    return intent
            elif kw in low:
                return intent
    return "unknown"


def _tokens(text):
    return {w for w in re.split(r"[\s.,!?;:()\"'/-]+", text.lower()) if len(w) >= 3 and w not in STOP}


def retrieve(user_text, docs):
    """Naive keyword-overlap retrieval over the agent's knowledge docs (stand-in for vector search)."""
    q = _tokens(user_text)
    best, best_score = None, 0
    for d in docs:
        score = len(q & _tokens(d["title"] + " " + d["content"]))
        if score > best_score:
            best, best_score = d, score
    return best if best_score >= 2 else None


# ----------------------------------------------------------------------------- providers
class MockSTT(STTProvider):
    note = "Simulated: treats the caller's text as the 'audio'. Supports stt_flaky / stt_failure scenarios."

    def transcribe(self, audio, language, ctx):
        sc = ctx.get("scenario")
        if sc == "stt_failure" or (sc == "stt_flaky" and ctx.get("attempt", 0) == 0):
            raise ProviderError("STT timeout (simulated)")
        text = audio if isinstance(audio, str) else audio.decode("utf-8", "ignore")
        return {"text": text, "confidence": round(0.90 + (zlib.crc32(text.encode()) % 100) / 1000, 3),
                "latency_ms": _jitter(text, 120)}


class MockLLM(LLMProvider):
    note = "Simulated: keyword intents + knowledge-base overlap. Not a language model."

    def respond(self, ctx):
        sc = ctx.get("scenario")
        if sc == "llm_timeout" or (sc == "llm_flaky" and ctx.get("attempt", 0) == 0):
            raise ProviderError("LLM timeout (simulated)")
        lang, company, text = ctx["language"], ctx["company"], ctx["user_text"]
        intent = detect_intent(text)
        if sc == "handover" and intent in ("price", "booking"):
            intent = "human"
        handover = intent == "human"
        if intent in ("price", "hours", "booking"):
            doc = retrieve(text, ctx.get("knowledge", []))
            reply = (doc["content"][:240]) if doc else t(intent, lang)
        elif intent in ("bye", "human"):
            reply = t(intent, lang, company=company)
        elif intent == "greet":
            reply = t("greeting", lang, company=company)
        else:
            doc = retrieve(text, ctx.get("knowledge", []))
            reply = doc["content"][:240] if doc else t("fallback", lang)
            intent = "knowledge" if doc else "unknown"
        return {"text": reply, "intent": intent, "handover": handover, "latency_ms": _jitter(text, 350, 250)}

    def summarize(self, ctx):
        topics = [i for i in ctx["intents"] if i not in ("greet", "unknown", "bye")]
        topics = list(dict.fromkeys(topics)) or ["general enquiry"]
        outcome = {"transferred": "transferred to a human agent", "completed": "completed normally"}.get(ctx["status"], ctx["status"])
        return (f"{ctx['direction'].capitalize()} call ({ctx['language']}) about: {', '.join(topics)}. "
                f"{ctx['turns']} turns, outcome: {outcome}.")


class MockTTS(TTSProvider):
    note = "Simulated: estimates speech duration; the recording contains placeholder tones, not speech."

    def synthesize(self, text, language, voice, ctx):
        return {"duration_ms": max(600, len(text) * 62), "latency_ms": _jitter(text, 90, 60)}


class MockTelephony(TelephonyProvider):
    note = "Simulated call lifecycle (ringing/answer/busy/no answer/failure) and SIP transfer. No real phone network."

    def place_call(self, from_number, to_number, direction, ctx):
        sc = ctx.get("scenario", "normal")
        sid = "MOCK" + format(zlib.crc32(f"{from_number}{to_number}{ctx.get('seed', '')}".encode()), "08x")
        status = {"no_answer": "no_answer", "busy": "busy", "network_failure": "failed"}.get(sc, "connected")
        return {"status": status, "sid": sid}

    def transfer(self, sid, target):
        return {"status": "bridged", "sip_uri": f"sip:{target.replace(' ', '')}@mock-sip.invalid"}


def sentiment(texts):
    low = " ".join(texts).lower()
    score = sum(low.count(w) for w in POS) - 2 * sum(low.count(w) for w in NEG)
    return "positive" if score > 0 else "negative" if score < 0 else "neutral"
