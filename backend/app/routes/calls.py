"""Calls: history, transcripts, recordings, live monitor (read for clients), simulation/live control (super admin)."""
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, request, send_file

from .. import db
from ..engine import orchestrator
from ..engine.providers import ProviderError
from ..engine.providers.mock import SCENARIOS
from ..security import auth_required, body, company_scope, fail, get_owned, is_admin

bp = Blueprint("calls", __name__, url_prefix="/api/calls")
SA = auth_required("super_admin")


def _where():
    """Tenant-safe filter. Clients never see test calls."""
    cid = company_scope(request.args.get("company_id"))
    cond, args = [], []
    if cid:
        cond.append("k.company_id=?"); args.append(cid)
    test = request.args.get("test", "all" if is_admin() else "none")
    if not is_admin():
        test = "none"
    if test == "none":
        cond.append("k.is_test=0")
    elif test == "only":
        cond.append("k.is_test=1")
    for key, col in (("agent_id", "k.agent_id"), ("status", "k.status"), ("direction", "k.direction")):
        if request.args.get(key):
            cond.append(f"{col}=?"); args.append(request.args[key])
    if request.args.get("q"):
        cond.append("(k.from_number LIKE ? OR k.to_number LIKE ? OR k.summary LIKE ?)")
        args += [f"%{request.args['q']}%"] * 3
    return (" WHERE " + " AND ".join(cond)) if cond else "", args


@bp.get("")
@auth_required()
def list_calls():
    where, args = _where()
    limit, offset = min(int(request.args.get("limit", 50)), 200), max(int(request.args.get("offset", 0)), 0)
    total = db.query("SELECT COUNT(*) c FROM calls k" + where, args, one=True)["c"]
    rows = db.query("SELECT k.*, a.name AS agent_name, c.name AS company_name FROM calls k JOIN agents a ON a.id=k.agent_id "
                    "JOIN companies c ON c.id=k.company_id" + where + " ORDER BY k.started_at DESC, k.id DESC LIMIT ? OFFSET ?", (*args, limit, offset))
    return jsonify(items=rows, total=total)


@bp.get("/live")
@auth_required()
def live():
    where, args = _where()
    where = (where + " AND " if where else " WHERE ") + "k.status='in_progress'"
    rows = db.query("SELECT k.*, a.name AS agent_name, c.name AS company_name, "
                    "(SELECT COUNT(*) FROM call_turns t WHERE t.call_id=k.id) AS turns FROM calls k JOIN agents a ON a.id=k.agent_id "
                    "JOIN companies c ON c.id=k.company_id" + where + " ORDER BY k.started_at DESC", args)
    return jsonify(items=rows)


@bp.get("/<int:cid>")
@auth_required()
def get_call(cid):
    c = get_owned("calls", cid)
    if c["is_test"] and not is_admin():
        fail("Not found", 404)
    c["agent_name"] = db.query("SELECT name FROM agents WHERE id=?", (c["agent_id"],), one=True)["name"]
    c["turns"] = db.query("SELECT seq,speaker,text,intent,confidence,latency_ms,duration_ms,ts FROM call_turns WHERE call_id=? ORDER BY seq", (cid,))
    return jsonify(c)


@bp.get("/<int:cid>/recording")
@auth_required()
def recording(cid):
    c = get_owned("calls", cid)
    if (c["is_test"] and not is_admin()) or not c["recording_file"]:
        fail("Not found", 404)
    path = Path(current_app.config["RECORDINGS_DIR"]) / Path(c["recording_file"]).name   # .name blocks path traversal
    if not path.exists():
        fail("Recording file missing", 404)
    return send_file(path, mimetype="audio/wav")


def _validate_call_body(d):
    agent = get_owned("agents", d.get("agent_id"))
    scenario = d.get("scenario", "normal")
    if scenario not in SCENARIOS:
        fail("Unknown scenario")
    direction = d.get("direction", "inbound")
    if direction not in ("inbound", "outbound"):
        fail("Invalid direction")
    is_test = bool(d.get("is_test", False))
    if not is_test and agent["status"] != "deployed":
        fail("Only deployed agents can take real (non-test) calls. Deploy it or mark the call as a test.")
    return agent, scenario, direction, is_test


@bp.post("/simulate")
@SA
def simulate():
    d = body()
    agent, scenario, direction, is_test = _validate_call_body(d)
    lines = d.get("utterances")
    if lines is not None and (not isinstance(lines, list) or len(lines) > 20):
        fail("utterances must be a list of up to 20 lines")
    call = orchestrator.simulate_call(agent, direction, str(d.get("number", "+91 98250 12345"))[:30], scenario, lines, is_test)
    db.audit(g.user, "call_simulated", "call", call["id"], f"{scenario} -> {call['status']}", company_id=agent["company_id"])
    return jsonify(call), 201


@bp.post("/start")
@SA
def start():
    d = body()
    agent, scenario, direction, is_test = _validate_call_body(d)
    cid = orchestrator.start_call(agent, direction, str(d.get("number", "+91 98250 12345"))[:30], scenario, is_test)
    db.audit(g.user, "call_started", "call", cid, scenario, company_id=agent["company_id"])
    return jsonify(get_call_dict(cid)), 201


def get_call_dict(cid):
    c = db.query("SELECT * FROM calls WHERE id=?", (cid,), one=True)
    c["turns"] = db.query("SELECT seq,speaker,text,intent,ts FROM call_turns WHERE call_id=? ORDER BY seq", (cid,))
    return c


@bp.post("/<int:cid>/step")
@SA
def step(cid):
    get_owned("calls", cid)
    text = str(body().get("text", "")).strip()
    if not text:
        fail("text is required")
    try:
        orchestrator.handle_utterance(cid, text[:500])
    except ProviderError as e:
        fail(str(e), 409)
    return jsonify(get_call_dict(cid))


@bp.post("/<int:cid>/end")
@SA
def end(cid):
    get_owned("calls", cid)
    orchestrator.end_call(cid)
    return jsonify(get_call_dict(cid))
