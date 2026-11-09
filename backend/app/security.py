"""JWT auth, role checks and company-level tenant isolation helpers."""
import datetime as dt
import functools

import jwt
from flask import current_app, g, request

from . import db


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


def fail(message, status=400):
    raise ApiError(message, status)


def issue_token(user):
    hours = int(current_app.config.get("JWT_HOURS", 12))
    now = dt.datetime.now(dt.timezone.utc)
    return jwt.encode({"sub": str(user["id"]), "iat": now, "exp": now + dt.timedelta(hours=hours)},
                      current_app.config["SECRET_KEY"], algorithm="HS256")


def auth_required(*roles):
    """Require a valid token; optionally restrict to roles. Role/company always re-read from DB."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            hdr = request.headers.get("Authorization", "")
            if not hdr.startswith("Bearer "):
                fail("Authentication required", 401)
            try:
                data = jwt.decode(hdr[7:], current_app.config["SECRET_KEY"], algorithms=["HS256"])
                user = db.query("SELECT * FROM users WHERE id=?", (int(data["sub"]),), one=True)
            except (jwt.PyJWTError, ValueError, KeyError):
                fail("Invalid or expired token", 401)
            if not user or not user["active"]:
                fail("Account disabled", 401)
            if user["company_id"]:
                co = db.query("SELECT status FROM companies WHERE id=?", (user["company_id"],), one=True)
                if not co or co["status"] != "active":
                    fail("Company account suspended", 403)
            if roles and user["role"] not in roles:
                fail("You do not have permission to do this", 403)
            g.user = user
            return fn(*a, **kw)
        return wrapper
    return deco


def is_admin():
    return g.user["role"] == "super_admin"


def company_scope(requested=None):
    """Clients are ALWAYS pinned to their own company. Super admins may filter by ?company_id."""
    if not is_admin():
        return g.user["company_id"]
    try:
        return int(requested) if requested not in (None, "") else None
    except ValueError:
        fail("Invalid company_id")


def get_owned(table, row_id):
    """Fetch a company-owned row; clients get 404 (not 403) for other tenants' rows to avoid leaking existence."""
    assert table in {"agents", "calls", "invoices", "tickets"}
    row = db.query(f"SELECT * FROM {table} WHERE id=?", (row_id,), one=True)
    if not row or (not is_admin() and row["company_id"] != g.user["company_id"]):
        fail("Not found", 404)
    return row


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        fail("JSON body required")
    return data


def pick(data, allowed):
    return {k: data[k] for k in allowed if k in data}


def safe_user(u):
    return {k: u[k] for k in ("id", "company_id", "name", "email", "role", "active", "created_at")}
