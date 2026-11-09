"""SQLite access layer + tiny SQL-file migration runner (schema_migrations table)."""
import sqlite3
from datetime import datetime, timezone

from flask import current_app, g

from . import config


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = [dict(r) for r in cur.fetchall()]
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    conn = get_db()
    cur = conn.execute(sql, args)
    conn.commit()
    return cur.lastrowid


def run_migrations():
    """Apply every migrations/*.sql not yet recorded. Returns list of applied names."""
    conn = get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
    applied = []
    for f in sorted(config.MIGRATIONS_DIR.glob("*.sql")):
        if f.name in done:
            continue
        conn.executescript(f.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations VALUES (?,?)", (f.name, now()))
        conn.commit()
        applied.append(f.name)
    return applied


def audit(user, action, entity="", entity_id=None, detail="", company_id=None):
    uid = user["id"] if user else None
    cid = company_id if company_id is not None else (user or {}).get("company_id")
    execute("INSERT INTO audit_logs(user_id,company_id,action,entity,entity_id,detail,created_at) VALUES (?,?,?,?,?,?,?)",
            (uid, cid, action, entity, entity_id, detail[:500], now()))


def notify_company(company_id, title, body=""):
    for u in query("SELECT id FROM users WHERE company_id=? AND active=1", (company_id,)):
        execute("INSERT INTO notifications(user_id,title,body,created_at) VALUES (?,?,?,?)", (u["id"], title, body, now()))


def notify_admins(title, body=""):
    for u in query("SELECT id FROM users WHERE role='super_admin' AND active=1"):
        execute("INSERT INTO notifications(user_id,title,body,created_at) VALUES (?,?,?,?)", (u["id"], title, body, now()))
