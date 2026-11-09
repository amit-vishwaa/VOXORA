"""Analytics, billing, notifications, support tickets."""
import math
from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request

from .. import db
from ..security import auth_required, body, company_scope, fail, get_owned, is_admin

bp = Blueprint("business", __name__, url_prefix="/api")
SA = auth_required("super_admin")


# ---------------------------------------------------------------- analytics
@bp.get("/analytics/overview")
@auth_required()
def analytics():
    cid = company_scope(request.args.get("company_id"))
    days = max(1, min(int(request.args.get("days", 30)), 365))
    since = (db.utcnow() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    cond, args = "k.is_test=0 AND k.started_at >= ?", [since]
    if cid:
        cond += " AND k.company_id=?"; args.append(cid)
    one = lambda sql, a=args: db.query(sql, a, one=True)
    t = one(f"""SELECT COUNT(*) calls,
        SUM(CASE WHEN status IN ('completed','transferred') THEN 1 ELSE 0 END) answered,
        SUM(CASE WHEN status IN ('failed','no_answer','busy') THEN 1 ELSE 0 END) missed,
        SUM(handover) handovers, COALESCE(SUM(billable_minutes),0) minutes,
        COALESCE(AVG(CASE WHEN duration_sec>0 THEN duration_sec END),0) avg_duration,
        COALESCE(SUM(errors),0) provider_errors FROM calls k WHERE {cond}""")
    by_day = {r["d"]: r for r in db.query(f"SELECT substr(started_at,1,10) d, COUNT(*) calls, COALESCE(SUM(billable_minutes),0) minutes FROM calls k WHERE {cond} GROUP BY d", args)}
    series = []
    for i in range(days):
        d = (db.utcnow() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        series.append({"date": d, "calls": by_day.get(d, {}).get("calls", 0), "minutes": by_day.get(d, {}).get("minutes", 0)})
    by_agent = db.query(f"SELECT a.name, COUNT(*) calls, COALESCE(SUM(k.billable_minutes),0) minutes FROM calls k JOIN agents a ON a.id=k.agent_id WHERE {cond} GROUP BY a.id ORDER BY calls DESC LIMIT 8", args)
    sent = {r["sentiment"]: r["n"] for r in db.query(f"SELECT sentiment, COUNT(*) n FROM calls k WHERE {cond} AND status IN ('completed','transferred') GROUP BY sentiment", args)}
    status = {r["status"]: r["n"] for r in db.query(f"SELECT status, COUNT(*) n FROM calls k WHERE {cond} GROUP BY status", args)}
    agents_q = "SELECT COUNT(*) c FROM agents WHERE status='deployed'" + (" AND company_id=?" if cid else "")
    out = {"days": days, "totals": {k: (v or 0) for k, v in t.items()}, "series": series, "by_agent": by_agent, "sentiment": sent,
           "status": status, "deployed_agents": db.query(agents_q, (cid,) if cid else (), one=True)["c"]}
    out["totals"]["avg_duration"] = round(out["totals"]["avg_duration"])
    out["totals"]["success_rate"] = round(100 * out["totals"]["answered"] / out["totals"]["calls"], 1) if out["totals"]["calls"] else 0
    if is_admin() and not cid:
        out["companies"] = db.query("SELECT COUNT(*) c FROM companies WHERE status='active'", one=True)["c"]
    return jsonify(out)


# ---------------------------------------------------------------- billing
def build_invoice(company_id, period):
    co = db.query("SELECT * FROM companies WHERE id=?", (company_id,), one=True)
    plan = db.query("SELECT * FROM plans WHERE code=?", (co["plan"],), one=True)
    used = db.query("SELECT COALESCE(SUM(billable_minutes),0) m FROM calls WHERE company_id=? AND is_test=0 AND substr(started_at,1,7)=?", (company_id, period), one=True)["m"]
    over = max(0, used - plan["included_minutes"])
    usage = round(over * plan["per_minute_rate"], 2)
    total = round(plan["monthly_fee"] + usage, 2)
    existing = db.query("SELECT * FROM invoices WHERE company_id=? AND period=?", (company_id, period), one=True)
    vals = (plan["code"], plan["monthly_fee"], plan["included_minutes"], used, over, plan["per_minute_rate"], usage, total)
    if existing:
        if existing["status"] != "draft":
            fail("Invoice already issued; it cannot be regenerated", 409)
        db.execute("UPDATE invoices SET plan=?,subscription_fee=?,included_minutes=?,minutes_used=?,overage_minutes=?,per_minute_rate=?,usage_amount=?,total=? WHERE id=?", (*vals, existing["id"]))
        return existing["id"]
    return db.execute("INSERT INTO invoices(company_id,period,plan,subscription_fee,included_minutes,minutes_used,overage_minutes,per_minute_rate,usage_amount,total,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (company_id, period, *vals, db.now()))


@bp.get("/billing/invoices")
@auth_required()
def invoices():
    cid = company_scope(request.args.get("company_id"))
    rows = db.query("SELECT i.*, c.name AS company_name FROM invoices i JOIN companies c ON c.id=i.company_id" + (" WHERE i.company_id=?" if cid else "")
                    + " ORDER BY i.period DESC, i.id DESC", (cid,) if cid else ())
    if not is_admin():
        rows = [r for r in rows if r["status"] != "draft"]   # clients only see issued/paid invoices
    return jsonify(items=rows)


@bp.get("/billing/usage")
@auth_required()
def usage():
    """Current-month usage vs plan allowance (clients: own company)."""
    cid = company_scope(request.args.get("company_id"))
    if not cid:
        fail("company_id required", 400)
    co = db.query("SELECT * FROM companies WHERE id=?", (cid,), one=True)
    plan = db.query("SELECT * FROM plans WHERE code=?", (co["plan"],), one=True)
    period = db.utcnow().strftime("%Y-%m")
    used = db.query("SELECT COALESCE(SUM(billable_minutes),0) m, COUNT(*) n FROM calls WHERE company_id=? AND is_test=0 AND substr(started_at,1,7)=?", (cid, period), one=True)
    over = max(0, used["m"] - plan["included_minutes"])
    return jsonify(period=period, plan=plan, minutes_used=used["m"], calls=used["n"], overage_minutes=over,
                   estimated_total=round(plan["monthly_fee"] + over * plan["per_minute_rate"], 2))


@bp.post("/billing/generate")
@SA
def generate():
    d = body()
    period = str(d.get("period", db.utcnow().strftime("%Y-%m")))
    try:
        datetime.strptime(period, "%Y-%m")
    except ValueError:
        fail("period must look like 2026-10")
    ids = []
    for co in db.query("SELECT id FROM companies WHERE status='active'"):
        if d.get("company_id") and int(d["company_id"]) != co["id"]:
            continue
        try:
            ids.append(build_invoice(co["id"], period))
        except Exception as e:  # already-issued invoice -> skip
            if getattr(e, "status", 0) != 409:
                raise
    db.audit(g.user, "invoices_generated", "invoice", None, f"{period}: {len(ids)}")
    return jsonify(generated=len(ids), period=period), 201


@bp.post("/billing/invoices/<int:iid>/status")
@SA
def invoice_status(iid):
    inv = get_owned("invoices", iid)
    st = body().get("status")
    if st not in ("issued", "paid"):
        fail("status must be issued or paid")
    db.execute("UPDATE invoices SET status=? WHERE id=?", (st, iid))
    db.audit(g.user, f"invoice_{st}", "invoice", iid, inv["period"], company_id=inv["company_id"])
    if st == "issued":
        db.notify_company(inv["company_id"], f"Invoice {inv['period']} issued", f"Total: INR {inv['total']:,.2f}")
    return jsonify(db.query("SELECT * FROM invoices WHERE id=?", (iid,), one=True))


# ---------------------------------------------------------------- notifications
@bp.get("/notifications")
@auth_required()
def notifications():
    rows = db.query("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50", (g.user["id"],))
    return jsonify(items=rows, unread=sum(1 for r in rows if not r["is_read"]))


@bp.post("/notifications/read")
@auth_required()
def read_all():
    db.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (g.user["id"],))
    return jsonify(ok=True)


# ---------------------------------------------------------------- support tickets
@bp.get("/tickets")
@auth_required()
def tickets():
    cid = company_scope(request.args.get("company_id"))
    rows = db.query("SELECT t.*, c.name AS company_name, u.name AS user_name FROM tickets t JOIN companies c ON c.id=t.company_id JOIN users u ON u.id=t.user_id"
                    + (" WHERE t.company_id=?" if cid else "") + " ORDER BY t.id DESC", (cid,) if cid else ())
    return jsonify(items=rows)


@bp.post("/tickets")
@auth_required("client")
def create_ticket():
    d = body()
    subject, text = str(d.get("subject", "")).strip(), str(d.get("body", "")).strip()
    if not subject or not text:
        fail("Subject and message are required")
    n = db.now()
    tid = db.execute("INSERT INTO tickets(company_id,user_id,subject,body,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                     (g.user["company_id"], g.user["id"], subject[:200], text[:4000], n, n))
    db.notify_admins("New support ticket", subject[:200])
    return jsonify(db.query("SELECT * FROM tickets WHERE id=?", (tid,), one=True)), 201


@bp.patch("/tickets/<int:tid>")
@SA
def update_ticket(tid):
    t = get_owned("tickets", tid)
    d = body()
    status = d.get("status", t["status"])
    if status not in ("open", "in_progress", "resolved"):
        fail("Invalid status")
    db.execute("UPDATE tickets SET status=?, response=?, updated_at=? WHERE id=?", (status, str(d.get("response", t["response"]))[:4000], db.now(), tid))
    db.notify_company(t["company_id"], f"Ticket updated: {t['subject']}", f"Status: {status}")
    return jsonify(db.query("SELECT * FROM tickets WHERE id=?", (tid,), one=True))
