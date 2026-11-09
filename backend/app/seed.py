"""Sample development data. Every call below is SIMULATED by the mock providers. Passwords come from env vars."""
import os
import random
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from . import db
from .engine import orchestrator
from .routes.business import build_invoice


def admin_creds():
    return os.environ.get("SEED_ADMIN_EMAIL", "admin@voxora.local"), os.environ.get("SEED_ADMIN_PASSWORD", "ChangeMe-Admin1")


def client_password():
    return os.environ.get("SEED_CLIENT_PASSWORD", "ChangeMe-Client1")


COMPANIES = [
    ("Sunrise Realty", "real_estate", "growth", "client@sunrise.local"),
    ("CareFirst Clinic", "healthcare", "starter", "client@carefirst.local"),
    ("BrightPath Academy", "education", "starter", "client@brightpath.local"),
]
AGENTS = [  # company idx, name, lang, status, kb
    (0, "Riya - Property Enquiries", "en", "deployed", [("Site visits", "Site visits are available Monday to Saturday between 10 AM and 6 PM. Please book at least one day in advance."),
                                                         ("Pricing", "Our 2 BHK apartments start at 45 lakh and 3 BHK apartments start at 68 lakh. Booking amount is 1 lakh.")]),
    (0, "Mehul - Gujarati Support", "gu", "deployed", [("Site visits", "સાઇટ વિઝિટ સોમવારથી શનિવાર સવારે 10 થી સાંજે 6 સુધી ઉપલબ્ધ છે.")]),
    (1, "Asha - Clinic Reception", "hi", "deployed", [("Doctor timings", "Doctor consultation timing is 9 AM to 1 PM and 5 PM to 8 PM. Consultation fee is 500 rupees."),
                                                      ("Appointments", "Appointments can be booked by phone, at least two hours before the slot.")]),
    (2, "Neel - Admissions", "en", "testing", [("Admissions", "Admissions for the new academic year open in March. Annual fee is 85000 rupees for primary classes.")]),
]
SCEN = ["normal"] * 14 + ["handover", "no_answer", "busy", "stt_flaky", "llm_timeout", "network_failure"]


def seed():
    if db.query("SELECT 1 FROM users LIMIT 1"):
        return False
    rnd = random.Random(42)
    n = db.now()
    email, pw = admin_creds()
    db.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES (?,?,?,?,?)", ("Voxora Admin", email, generate_password_hash(pw), "super_admin", n))
    cids = []
    for name, ind, plan, cemail in COMPANIES:
        cid = db.execute("INSERT INTO companies(name,industry,plan,contact_email,created_at) VALUES (?,?,?,?,?)", (name, ind, plan, cemail, n))
        cids.append(cid)
        db.execute("INSERT INTO users(company_id,name,email,password_hash,role,created_at) VALUES (?,?,?,?,?,?)",
                   (cid, name + " Manager", cemail, generate_password_hash(client_password()), "client", n))
    admin = db.query("SELECT * FROM users WHERE role='super_admin'", one=True)
    agents = []
    for ci, name, lang, status, kb in AGENTS:
        ind = COMPANIES[ci][1]
        voice = {"en": "en-female-1", "hi": "hi-female-1", "gu": "gu-male-1"}[lang]
        aid = db.execute("INSERT INTO agents(company_id,name,industry,language,voice,prompt,phone_number,handover_number,status,deployed_version,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (cids[ci], name, ind, lang, voice, f"You are a polite voice assistant for a {ind.replace('_', ' ')} business. Keep answers short.",
                          f"+91 79 4000 {1000 + aid_seed()}", "+91 98250 99999", status, 1 if status == "deployed" else None, n, n))
        db.execute("INSERT INTO agent_versions(agent_id,version,snapshot,note,created_by,created_at) VALUES (?,?,?,?,?,?)",
                   (aid, 1, "{}", "Initial version (seed)", admin["id"], n))
        for title, content in kb:
            db.execute("INSERT INTO knowledge_docs(agent_id,title,content,created_at) VALUES (?,?,?,?)", (aid, title, content, n))
        agents.append(db.query("SELECT * FROM agents WHERE id=?", (aid,), one=True))
    # snapshot rows need real content for rollback to work
    import json
    from .routes.agents import CONFIG_FIELDS
    for a in agents:
        db.execute("UPDATE agent_versions SET snapshot=? WHERE agent_id=? AND version=1", (json.dumps({k: a[k] for k in CONFIG_FIELDS}, ensure_ascii=False), a["id"]))
    deployed = [a for a in agents if a["status"] == "deployed"]
    base = db.utcnow()
    for _ in range(110):
        a = rnd.choice(deployed)
        when = base - timedelta(days=rnd.randint(0, 34), hours=rnd.randint(0, 9), minutes=rnd.randint(0, 59))
        orchestrator.simulate_call(a, rnd.choice(["inbound", "inbound", "outbound"]), f"+91 9{rnd.randint(100000000, 999999999)}",
                                   rnd.choice(SCEN), started_at=when.strftime("%Y-%m-%d %H:%M:%S"))
    # one live call + one test call for demo
    orchestrator.start_call(deployed[0], "inbound", "+91 98765 43210")
    orchestrator.simulate_call(agents[3], is_test=True)
    last = (base.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    for cid in cids:
        iid = build_invoice(cid, last)
        db.execute("UPDATE invoices SET status='issued' WHERE id=?", (iid,))
        build_invoice(cid, base.strftime("%Y-%m"))
    cu = db.query("SELECT * FROM users WHERE role='client' ORDER BY id", one=True)
    db.execute("INSERT INTO tickets(company_id,user_id,subject,body,created_at,updated_at) VALUES (?,?,?,?,?,?)",
               (cu["company_id"], cu["id"], "Need weekend support hours", "Can the agent also answer calls on Sundays?", n, n))
    db.notify_company(cids[0], "Welcome to Voxora", "Your dashboard is ready.")
    db.notify_admins("Seed data loaded", "Simulated development data was created.")
    return True


_counter = [0]


def aid_seed():
    _counter[0] += 1
    return _counter[0]
