from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

from .. import db
from ..security import auth_required, body, fail, issue_token, safe_user

bp = Blueprint("auth", __name__, url_prefix="/api/auth")
MAX_FAILS, LOCK_MIN = 5, 5
FMT = "%Y-%m-%d %H:%M:%S"


def check_new_password(pw):
    if not isinstance(pw, str) or len(pw) < 8:
        fail("Password must be at least 8 characters")


@bp.post("/login")
def login():
    d = body()
    email, pw = str(d.get("email", "")).strip(), str(d.get("password", ""))
    u = db.query("SELECT * FROM users WHERE email=?", (email,), one=True)
    if u and u["locked_until"] and u["locked_until"] > db.now():
        fail("Too many failed attempts. Try again in a few minutes.", 429)
    if not u or not u["active"] or not check_password_hash(u["password_hash"], pw):
        if u:
            fails = u["failed_logins"] + 1
            lock = (db.utcnow() + timedelta(minutes=LOCK_MIN)).strftime(FMT) if fails >= MAX_FAILS else None
            db.execute("UPDATE users SET failed_logins=?, locked_until=? WHERE id=?", (0 if lock else fails, lock, u["id"]))
        db.audit(u, "login_failed", "user", u["id"] if u else None, email, company_id=u["company_id"] if u else None)
        fail("Invalid email or password", 401)
    db.execute("UPDATE users SET failed_logins=0, locked_until=NULL WHERE id=?", (u["id"],))
    db.audit(u, "login", "user", u["id"])
    return jsonify(token=issue_token(u), user=safe_user(u))


@bp.get("/me")
@auth_required()
def me():
    u = safe_user(g.user)
    if g.user["company_id"]:
        u["company"] = db.query("SELECT id,name,industry,plan FROM companies WHERE id=?", (g.user["company_id"],), one=True)
    return jsonify(user=u)


@bp.post("/change-password")
@auth_required()
def change_password():
    d = body()
    if not check_password_hash(g.user["password_hash"], str(d.get("current", ""))):
        fail("Current password is incorrect", 400)
    check_new_password(d.get("new"))
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(d["new"]), g.user["id"]))
    db.audit(g.user, "password_changed", "user", g.user["id"])
    return jsonify(ok=True)
