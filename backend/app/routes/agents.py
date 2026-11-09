"""Agents: CRUD (super admin), versioning, knowledge base, test/approve/deploy/rollback workflow.
Clients get a read-only, redacted view (no prompt, no provider config) and may only approve/reject."""
import json

from flask import Blueprint, g, jsonify

from .. import config, db
from ..engine import orchestrator, providers
from ..engine.providers.mock import SCENARIOS
from ..security import auth_required, body, fail, get_owned, is_admin, pick, company_scope
from flask import request

bp = Blueprint("agents", __name__, url_prefix="/api")
SA = auth_required("super_admin")
CONFIG_FIELDS = ["name", "industry", "language", "voice", "greeting", "prompt", "stt_provider", "llm_provider",
                 "tts_provider", "telephony_provider", "phone_number", "handover_number"]
CLIENT_FIELDS = ["id", "company_id", "name", "industry", "language", "status", "current_version", "deployed_version",
                 "phone_number", "created_at", "updated_at"]


def view(a):
    if is_admin():
        return a
    out = {k: a[k] for k in CLIENT_FIELDS}
    return out


def validate(d, partial=False):
    if not partial or "name" in d:
        if not str(d.get("name", "")).strip():
            fail("Agent name is required")
    if "industry" in d and d["industry"] not in config.INDUSTRIES:
        fail("Invalid industry")
    if "language" in d and d["language"] not in config.LANGUAGES:
        fail("Language must be one of: " + ", ".join(config.LANGUAGES))
    for kind in ("stt", "llm", "tts", "telephony"):
        key = f"{kind}_provider"
        if key in d and not providers.exists(kind, d[key]):
            fail(f"Unknown {kind} provider '{d[key]}'")
    for k in CONFIG_FIELDS:
        if k in d and not isinstance(d[k], str):
            fail(f"{k} must be text")
        if k in d and len(d[k]) > 8000:
            fail(f"{k} is too long")


def snapshot(a):
    return json.dumps({k: a[k] for k in CONFIG_FIELDS}, ensure_ascii=False)


def save_version(agent_id, version, note):
    a = db.query("SELECT * FROM agents WHERE id=?", (agent_id,), one=True)
    db.execute("INSERT INTO agent_versions(agent_id,version,snapshot,note,created_by,created_at) VALUES (?,?,?,?,?,?)",
               (agent_id, version, snapshot(a), note, g.user["id"], db.now()))


@bp.get("/agents")
@auth_required()
def list_agents():
    cid = company_scope(request.args.get("company_id"))
    rows = db.query("""SELECT a.*, c.name AS company_name,
        (SELECT COUNT(*) FROM calls k WHERE k.agent_id=a.id AND k.is_test=0) AS total_calls,
        (SELECT COALESCE(SUM(billable_minutes),0) FROM calls k WHERE k.agent_id=a.id AND k.is_test=0) AS total_minutes
        FROM agents a JOIN companies c ON c.id=a.company_id""" + (" WHERE a.company_id=?" if cid else "") + " ORDER BY a.id DESC",
                    (cid,) if cid else ())
    return jsonify(items=[{**view(r), "company_name": r["company_name"], "total_calls": r["total_calls"],
                           "total_minutes": r["total_minutes"]} for r in rows])


@bp.post("/agents")
@SA
def create_agent():
    d = body()
    validate(d)
    if not db.query("SELECT 1 FROM companies WHERE id=?", (d.get("company_id"),)):
        fail("Valid company_id required")
    vals = {"industry": "other", "language": "en", "voice": config.VOICES.get(d.get("language", "en"), ["en-female-1"])[0],
            "greeting": "", "prompt": "", "stt_provider": "mock-stt", "llm_provider": "mock-llm", "tts_provider": "mock-tts",
            "telephony_provider": "mock-telephony", "phone_number": "", "handover_number": ""}
    vals.update(pick(d, CONFIG_FIELDS))
    if vals["voice"] not in config.VOICES[vals["language"]]:
        fail("Voice does not match the chosen language")
    n = db.now()
    aid = db.execute("INSERT INTO agents(company_id," + ",".join(CONFIG_FIELDS) + ",created_at,updated_at) VALUES (?," +
                     ",".join("?" * len(CONFIG_FIELDS)) + ",?,?)",
                     (d["company_id"], *[vals[k] for k in CONFIG_FIELDS], n, n))
    save_version(aid, 1, "Initial version")
    db.audit(g.user, "agent_created", "agent", aid, vals["name"], company_id=d["company_id"])
    return jsonify(get_owned("agents", aid)), 201


@bp.get("/agents/<int:aid>")
@auth_required()
def get_agent(aid):
    a = get_owned("agents", aid)
    out = view(a)
    out["company_name"] = db.query("SELECT name FROM companies WHERE id=?", (a["company_id"],), one=True)["name"]
    out["approvals"] = db.query("SELECT ap.*, u.name AS by_name FROM approvals ap LEFT JOIN users u ON u.id=ap.decided_by WHERE agent_id=? ORDER BY ap.id DESC LIMIT 10", (aid,))
    return jsonify(out)


@bp.patch("/agents/<int:aid>")
@SA
def update_agent(aid):
    a = get_owned("agents", aid)
    d = pick(body(), CONFIG_FIELDS)
    validate(d, partial=True)
    merged = {**a, **d}
    if merged["voice"] not in config.VOICES[merged["language"]]:
        fail("Voice does not match the chosen language")
    changed = [k for k in d if d[k] != a[k]]
    if not changed:
        return jsonify(a)
    version = a["current_version"] + 1
    status = "testing" if a["status"] in ("deployed", "approved", "pending_approval", "rejected") else a["status"]
    db.execute("UPDATE agents SET " + ",".join(f"{k}=?" for k in changed) + ",current_version=?,status=?,updated_at=? WHERE id=?",
               (*[d[k] for k in changed], version, status, db.now(), aid))
    save_version(aid, version, "Changed: " + ", ".join(changed))
    db.audit(g.user, "agent_updated", "agent", aid, f"v{version}: {', '.join(changed)}", company_id=a["company_id"])
    if a["status"] == "deployed":
        db.notify_company(a["company_id"], f"Agent '{a['name']}' changed", "A new version needs testing and approval before redeploy.")
    return jsonify(get_owned("agents", aid))


@bp.get("/agents/<int:aid>/versions")
@SA
def versions(aid):
    get_owned("agents", aid)
    rows = db.query("SELECT v.id,v.version,v.note,v.created_at,u.name AS by_name FROM agent_versions v LEFT JOIN users u ON u.id=v.created_by WHERE agent_id=? ORDER BY version DESC", (aid,))
    return jsonify(items=rows)


# ---- knowledge base
@bp.get("/agents/<int:aid>/knowledge")
@SA
def kb_list(aid):
    get_owned("agents", aid)
    return jsonify(items=db.query("SELECT * FROM knowledge_docs WHERE agent_id=? ORDER BY id DESC", (aid,)))


@bp.post("/agents/<int:aid>/knowledge")
@SA
def kb_add(aid):
    a = get_owned("agents", aid)
    d = body()
    title, content = str(d.get("title", "")).strip(), str(d.get("content", "")).strip()
    if not title or not content:
        fail("Title and content are required")
    if len(content) > 20000:
        fail("Content too long (max 20000 characters)")
    kid = db.execute("INSERT INTO knowledge_docs(agent_id,title,content,created_at) VALUES (?,?,?,?)", (aid, title, content, db.now()))
    db.audit(g.user, "knowledge_added", "agent", aid, title, company_id=a["company_id"])
    return jsonify(db.query("SELECT * FROM knowledge_docs WHERE id=?", (kid,), one=True)), 201


@bp.delete("/knowledge/<int:kid>")
@SA
def kb_delete(kid):
    k = db.query("SELECT k.*, a.company_id FROM knowledge_docs k JOIN agents a ON a.id=k.agent_id WHERE k.id=?", (kid,), one=True)
    if not k:
        fail("Not found", 404)
    db.execute("DELETE FROM knowledge_docs WHERE id=?", (kid,))
    db.audit(g.user, "knowledge_deleted", "agent", k["agent_id"], k["title"], company_id=k["company_id"])
    return jsonify(ok=True)


# ---- workflow
@bp.post("/agents/<int:aid>/test-call")
@SA
def test_call(aid):
    a = get_owned("agents", aid)
    d = request.get_json(silent=True) or {}
    scenario = d.get("scenario", "normal")
    if scenario not in SCENARIOS:
        fail("Unknown scenario")
    lines = d.get("utterances")
    if lines is not None and (not isinstance(lines, list) or len(lines) > 20):
        fail("utterances must be a list of up to 20 lines")
    call = orchestrator.simulate_call(a, d.get("direction", "inbound"), d.get("number", "+91 90000 11111"), scenario, lines, is_test=True)
    if a["status"] == "draft":
        db.execute("UPDATE agents SET status='testing', updated_at=? WHERE id=?", (db.now(), aid))
    db.audit(g.user, "test_call", "agent", aid, f"{scenario} -> {call['status']}", company_id=a["company_id"])
    return jsonify(call), 201


@bp.post("/agents/<int:aid>/request-approval")
@SA
def request_approval(aid):
    a = get_owned("agents", aid)
    if a["status"] not in ("testing", "rejected", "approved"):
        fail(f"Agent in status '{a['status']}' cannot be sent for approval")
    ok = db.query("SELECT 1 FROM calls WHERE agent_id=? AND is_test=1 AND agent_version=? AND status='completed'", (aid, a["current_version"]))
    if not ok:
        fail("Run at least one successful test call on the current version first")
    db.execute("UPDATE agents SET status='pending_approval', updated_at=? WHERE id=?", (db.now(), aid))
    db.audit(g.user, "approval_requested", "agent", aid, f"v{a['current_version']}", company_id=a["company_id"])
    db.notify_company(a["company_id"], f"Approval needed: {a['name']}", f"Version {a['current_version']} is ready for your review.")
    return jsonify(get_owned("agents", aid))


def decide(aid, decision):
    a = get_owned("agents", aid)
    if a["status"] != "pending_approval":
        fail("Agent is not waiting for approval")
    comment = str((request.get_json(silent=True) or {}).get("comment", ""))[:500]
    db.execute("INSERT INTO approvals(agent_id,version,decision,comment,decided_by,created_at) VALUES (?,?,?,?,?,?)",
               (aid, a["current_version"], decision, comment, g.user["id"], db.now()))
    db.execute("UPDATE agents SET status=?, updated_at=? WHERE id=?", ("approved" if decision == "approved" else "rejected", db.now(), aid))
    db.audit(g.user, f"agent_{decision}", "agent", aid, comment, company_id=a["company_id"])
    db.notify_admins(f"Agent {decision}: {a['name']}", comment or "No comment")
    return jsonify(view(get_owned("agents", aid)))


@bp.post("/agents/<int:aid>/approve")
@auth_required()
def approve(aid):
    return decide(aid, "approved")


@bp.post("/agents/<int:aid>/reject")
@auth_required()
def reject(aid):
    return decide(aid, "rejected")


@bp.post("/agents/<int:aid>/deploy")
@SA
def deploy(aid):
    a = get_owned("agents", aid)
    if a["status"] != "approved":
        fail("Only approved agents can be deployed")
    db.execute("UPDATE agents SET status='deployed', deployed_version=current_version, updated_at=? WHERE id=?", (db.now(), aid))
    db.audit(g.user, "agent_deployed", "agent", aid, f"v{a['current_version']}", company_id=a["company_id"])
    db.notify_company(a["company_id"], f"Agent live: {a['name']}", f"Version {a['current_version']} is now deployed.")
    return jsonify(get_owned("agents", aid))


@bp.post("/agents/<int:aid>/rollback")
@SA
def rollback(aid):
    a = get_owned("agents", aid)
    try:
        target = int(body().get("version"))
    except (TypeError, ValueError):
        fail("version is required")
    v = db.query("SELECT * FROM agent_versions WHERE agent_id=? AND version=?", (aid, target), one=True)
    if not v:
        fail("Version not found", 404)
    cfg = json.loads(v["snapshot"])
    new_version = a["current_version"] + 1
    db.execute("UPDATE agents SET " + ",".join(f"{k}=?" for k in cfg) + ",current_version=?,deployed_version=?,status='deployed',updated_at=? WHERE id=?",
               (*cfg.values(), new_version, new_version, db.now(), aid))
    save_version(aid, new_version, f"Rollback to v{target}")
    db.audit(g.user, "agent_rollback", "agent", aid, f"v{target} -> new v{new_version}", company_id=a["company_id"])
    db.notify_company(a["company_id"], f"Agent rolled back: {a['name']}", f"Restored configuration of version {target}.")
    return jsonify(get_owned("agents", aid))
