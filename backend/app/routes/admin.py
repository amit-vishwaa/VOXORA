"""Super-admin only: companies, users, providers, audit log, meta."""
from flask import Blueprint, g, jsonify, request
from werkzeug.security import generate_password_hash

from .. import config, db
from ..engine import providers
from ..engine.providers.mock import SCENARIOS
from ..security import auth_required, body, fail, pick, safe_user
from .auth import check_new_password

bp = Blueprint("admin", __name__, url_prefix="/api")
SA = auth_required("super_admin")


def _plan_ok(code):
    if not db.query("SELECT 1 FROM plans WHERE code=?", (code,)):
        fail("Unknown plan")


@bp.get("/meta")
@auth_required()
def meta():
    out = {"industries": config.INDUSTRIES, "languages": config.LANGUAGES, "voices": config.VOICES,
           "plans": db.query("SELECT * FROM plans"), "scenarios": SCENARIOS}
    if g.user["role"] == "super_admin":
        out["providers"] = providers.describe()
    return jsonify(out)


# ---- companies
@bp.get("/companies")
@SA
def companies():
    rows = db.query("""SELECT c.*, (SELECT COUNT(*) FROM agents a WHERE a.company_id=c.id) AS agents,
        (SELECT COUNT(*) FROM users u WHERE u.company_id=c.id) AS users,
        (SELECT COUNT(*) FROM calls k WHERE k.company_id=c.id AND k.is_test=0) AS calls FROM companies c ORDER BY c.name""")
    return jsonify(items=rows)


@bp.post("/companies")
@SA
def create_company():
    d = body()
    name = str(d.get("name", "")).strip()
    if not name:
        fail("Company name is required")
    industry, plan = d.get("industry", "other"), d.get("plan", "starter")
    if industry not in config.INDUSTRIES:
        fail("Invalid industry")
    _plan_ok(plan)
    if db.query("SELECT 1 FROM companies WHERE name=?", (name,)):
        fail("A company with this name already exists", 409)
    cid = db.execute("INSERT INTO companies(name,industry,plan,contact_email,created_at) VALUES (?,?,?,?,?)",
                     (name, industry, plan, d.get("contact_email", ""), db.now()))
    db.audit(g.user, "company_created", "company", cid, name, company_id=cid)
    return jsonify(db.query("SELECT * FROM companies WHERE id=?", (cid,), one=True)), 201


@bp.patch("/companies/<int:cid>")
@SA
def update_company(cid):
    if not db.query("SELECT 1 FROM companies WHERE id=?", (cid,)):
        fail("Not found", 404)
    d = pick(body(), ["name", "industry", "plan", "status", "contact_email"])
    if "industry" in d and d["industry"] not in config.INDUSTRIES:
        fail("Invalid industry")
    if "plan" in d:
        _plan_ok(d["plan"])
    if "status" in d and d["status"] not in ("active", "suspended"):
        fail("Invalid status")
    if d:
        db.execute("UPDATE companies SET " + ",".join(f"{k}=?" for k in d) + " WHERE id=?", (*d.values(), cid))
        db.audit(g.user, "company_updated", "company", cid, ",".join(d), company_id=cid)
    return jsonify(db.query("SELECT * FROM companies WHERE id=?", (cid,), one=True))


# ---- users
@bp.get("/users")
@SA
def users():
    cid = request.args.get("company_id")
    rows = db.query("SELECT u.*, c.name AS company_name FROM users u LEFT JOIN companies c ON c.id=u.company_id"
                    + (" WHERE u.company_id=?" if cid else "") + " ORDER BY u.id", (cid,) if cid else ())
    return jsonify(items=[{**safe_user(r), "company_name": r["company_name"]} for r in rows])


@bp.post("/users")
@SA
def create_user():
    d = body()
    role = d.get("role", "client")
    name, email = str(d.get("name", "")).strip(), str(d.get("email", "")).strip()
    if not name or "@" not in email:
        fail("Name and a valid email are required")
    check_new_password(d.get("password"))
    if role not in ("client", "super_admin"):
        fail("Invalid role")
    cid = d.get("company_id") if role == "client" else None
    if role == "client" and not db.query("SELECT 1 FROM companies WHERE id=?", (cid,)):
        fail("A valid company_id is required for client users")
    if db.query("SELECT 1 FROM users WHERE email=?", (email,)):
        fail("Email already in use", 409)
    uid = db.execute("INSERT INTO users(company_id,name,email,password_hash,role,created_at) VALUES (?,?,?,?,?,?)",
                     (cid, name, email, generate_password_hash(d["password"]), role, db.now()))
    db.audit(g.user, "user_created", "user", uid, f"{email} ({role})", company_id=cid)
    return jsonify(safe_user(db.query("SELECT * FROM users WHERE id=?", (uid,), one=True))), 201


@bp.patch("/users/<int:uid>")
@SA
def update_user(uid):
    u = db.query("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not u:
        fail("Not found", 404)
    d = body()
    if "active" in d:
        if uid == g.user["id"] and not d["active"]:
            fail("You cannot disable your own account")
        db.execute("UPDATE users SET active=? WHERE id=?", (int(bool(d["active"])), uid))
    if "name" in d and str(d["name"]).strip():
        db.execute("UPDATE users SET name=? WHERE id=?", (str(d["name"]).strip(), uid))
    if d.get("password"):
        check_new_password(d["password"])
        db.execute("UPDATE users SET password_hash=?, failed_logins=0, locked_until=NULL WHERE id=?", (generate_password_hash(d["password"]), uid))
    db.audit(g.user, "user_updated", "user", uid, ",".join(k for k in d if k != "password"), company_id=u["company_id"])
    return jsonify(safe_user(db.query("SELECT * FROM users WHERE id=?", (uid,), one=True)))


# ---- audit
@bp.get("/audit")
@SA
def audit_log():
    limit = min(int(request.args.get("limit", 100)), 500)
    rows = db.query("""SELECT a.*, u.email AS user_email, c.name AS company_name FROM audit_logs a
        LEFT JOIN users u ON u.id=a.user_id LEFT JOIN companies c ON c.id=a.company_id ORDER BY a.id DESC LIMIT ?""", (limit,))
    return jsonify(items=rows)
