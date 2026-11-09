"""Run: python -m unittest discover -s tests -v   (works with pytest too)"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import create_app, db  # noqa: E402
from app.seed import seed  # noqa: E402

ADMIN = ("admin@voxora.local", "ChangeMe-Admin1")
SUN = ("client@sunrise.local", "ChangeMe-Client1")
CARE = ("client@carefirst.local", "ChangeMe-Client1")


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for k in ("SEED_ADMIN_PASSWORD", "SEED_CLIENT_PASSWORD", "SEED_ADMIN_EMAIL"):
            os.environ.pop(k, None)
        cls.tmp = tempfile.mkdtemp()
        cls.app = create_app({"DATABASE": cls.tmp + "/t.db", "RECORDINGS_DIR": cls.tmp + "/rec", "SECRET_KEY": "test-secret-key-0123456789abcdef0123"})
        with cls.app.app_context():
            seed()
        cls.c = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def login(self, creds):
        r = self.c.post("/api/auth/login", json={"email": creds[0], "password": creds[1]})
        self.assertEqual(r.status_code, 200, r.data)
        return {"Authorization": "Bearer " + r.get_json()["token"]}

    def get(self, path, h):
        return self.c.get(path, headers=h)

    def post(self, path, h, data=None):
        return self.c.post(path, headers=h, json=data if data is not None else {})


class TestAuth(Base):
    def test_login_bad_password(self):
        self.assertEqual(self.c.post("/api/auth/login", json={"email": ADMIN[0], "password": "nope"}).status_code, 401)

    def test_requires_token(self):
        self.assertEqual(self.c.get("/api/agents").status_code, 401)
        self.assertEqual(self.c.get("/api/agents", headers={"Authorization": "Bearer junk"}).status_code, 401)

    def test_lockout(self):
        for _ in range(5):
            self.c.post("/api/auth/login", json={"email": CARE[0], "password": "wrong"})
        r = self.c.post("/api/auth/login", json={"email": CARE[0], "password": CARE[1]})
        self.assertEqual(r.status_code, 429)
        with self.app.app_context():
            db.execute("UPDATE users SET locked_until=NULL, failed_logins=0")


class TestRolesAndIsolation(Base):
    def test_client_cannot_use_admin_endpoints(self):
        h = self.login(SUN)
        for path in ("/api/companies", "/api/users", "/api/audit"):
            self.assertEqual(self.get(path, h).status_code, 403, path)
        self.assertEqual(self.post("/api/agents", h, {"name": "x", "company_id": 1}).status_code, 403)

    def test_client_sees_only_own_company(self):
        h = self.login(SUN)
        agents = self.get("/api/agents", h).get_json()["items"]
        self.assertTrue(agents and all(a["company_id"] == agents[0]["company_id"] for a in agents))
        # asking for another company via query string is ignored
        other = self.get("/api/agents?company_id=2", h).get_json()["items"]
        self.assertEqual({a["company_id"] for a in other}, {agents[0]["company_id"]})
        calls = self.get("/api/calls?company_id=2&limit=200", h).get_json()["items"]
        self.assertTrue(calls and {k["company_id"] for k in calls} == {agents[0]["company_id"]})

    def test_cross_tenant_objects_are_404(self):
        h = self.login(CARE)
        sun_agent = self.get("/api/agents", self.login(ADMIN)).get_json()["items"]
        sun_agent = [a for a in sun_agent if a["company_name"] == "Sunrise Realty"][0]
        self.assertEqual(self.get(f"/api/agents/{sun_agent['id']}", h).status_code, 404)
        self.assertEqual(self.post(f"/api/agents/{sun_agent['id']}/approve", h).status_code, 404)
        sun_call = [k for k in self.get("/api/calls?limit=200", self.login(ADMIN)).get_json()["items"]
                    if k["company_name"] == "Sunrise Realty" and k["recording_file"]][0]
        self.assertEqual(self.get(f"/api/calls/{sun_call['id']}", h).status_code, 404)
        self.assertEqual(self.get(f"/api/calls/{sun_call['id']}/recording", h).status_code, 404)

    def test_client_view_is_redacted_and_readonly(self):
        h = self.login(SUN)
        a = self.get("/api/agents", h).get_json()["items"][0]
        for secret in ("prompt", "stt_provider", "llm_provider", "handover_number"):
            self.assertNotIn(secret, a)
        self.assertEqual(self.c.patch(f"/api/agents/{a['id']}", headers=h, json={"name": "hack"}).status_code, 403)
        self.assertEqual(self.get(f"/api/agents/{a['id']}/versions", h).status_code, 403)

    def test_client_never_sees_test_calls(self):
        h = self.login(SUN)
        self.assertTrue(all(k["is_test"] == 0 for k in self.get("/api/calls?test=only&limit=200", h).get_json()["items"]))

    def test_analytics_scoped(self):
        a = self.get("/api/analytics/overview", self.login(ADMIN)).get_json()
        s = self.get("/api/analytics/overview?company_id=2", self.login(SUN)).get_json()
        self.assertLess(s["totals"]["calls"], a["totals"]["calls"])

    def test_billing_clients_see_only_issued_own(self):
        rows = self.get("/api/billing/invoices", self.login(SUN)).get_json()["items"]
        self.assertTrue(rows and all(r["status"] != "draft" and r["company_name"] == "Sunrise Realty" for r in rows))


class TestWorkflow(Base):
    def test_full_agent_lifecycle(self):
        adm, cl = self.login(ADMIN), self.login(SUN)
        co = self.get("/api/agents", cl).get_json()["items"][0]["company_id"]
        r = self.post("/api/agents", adm, {"name": "Lifecycle", "company_id": co, "language": "en", "industry": "real_estate"})
        self.assertEqual(r.status_code, 201)
        aid = r.get_json()["id"]
        self.assertEqual(self.post(f"/api/agents/{aid}/request-approval", adm).status_code, 400)    # needs a test first
        self.assertEqual(self.post("/api/calls/simulate", adm, {"agent_id": aid}).status_code, 400)  # not deployed
        t = self.post(f"/api/agents/{aid}/test-call", adm, {})
        self.assertEqual(t.get_json()["status"], "completed")
        self.assertEqual(self.post(f"/api/agents/{aid}/request-approval", adm).status_code, 200)
        self.assertEqual(self.post(f"/api/agents/{aid}/deploy", adm).status_code, 400)              # not approved yet
        self.assertEqual(self.post(f"/api/agents/{aid}/approve", cl).status_code, 200)
        self.assertEqual(self.post(f"/api/agents/{aid}/deploy", adm).get_json()["status"], "deployed")
        real = self.post("/api/calls/simulate", adm, {"agent_id": aid})
        self.assertEqual(real.status_code, 201)
        # edit -> new version, drops out of deployed, then rollback restores v1
        self.c.patch(f"/api/agents/{aid}", headers=adm, json={"name": "Lifecycle v2"})
        a = self.get(f"/api/agents/{aid}", adm).get_json()
        self.assertEqual((a["current_version"], a["status"]), (2, "testing"))
        rb = self.post(f"/api/agents/{aid}/rollback", adm, {"version": 1}).get_json()
        self.assertEqual((rb["name"], rb["status"], rb["current_version"]), ("Lifecycle", "deployed", 3))
        vers = self.get(f"/api/agents/{aid}/versions", adm).get_json()["items"]
        self.assertEqual([v["version"] for v in vers], [3, 2, 1])

    def test_validation(self):
        adm = self.login(ADMIN)
        self.assertEqual(self.post("/api/agents", adm, {"name": "x", "company_id": 1, "language": "fr"}).status_code, 400)
        self.assertEqual(self.post("/api/agents", adm, {"name": "x", "company_id": 1, "llm_provider": "nope"}).status_code, 400)
        self.assertEqual(self.post("/api/agents", adm, {"name": "x", "company_id": 1, "language": "hi", "voice": "en-male-1"}).status_code, 400)
        self.assertEqual(self.post("/api/users", adm, {"name": "A", "email": "a@b.c", "password": "short", "company_id": 1}).status_code, 400)

    def test_real_provider_stub_falls_back_to_handover(self):
        adm = self.login(ADMIN)
        co = self.get("/api/companies", adm).get_json()["items"][0]["id"]
        aid = self.post("/api/agents", adm, {"name": "Stub", "company_id": co, "llm_provider": "openai-llm"}).get_json()["id"]
        call = self.post(f"/api/agents/{aid}/test-call", adm, {}).get_json()
        self.assertEqual(call["status"], "transferred")


class TestSimulatedCalling(Base):
    def run_scenario(self, scenario, lang_agent=0):
        adm = self.login(ADMIN)
        agents = [a for a in self.get("/api/agents", adm).get_json()["items"] if a["status"] == "deployed"]
        return self.post("/api/calls/simulate", adm, {"agent_id": agents[lang_agent]["id"], "scenario": scenario}).get_json()

    def test_normal_completes_with_transcript_and_recording(self):
        call = self.run_scenario("normal")
        self.assertEqual(call["status"], "completed")
        self.assertGreater(call["duration_sec"], 0)
        adm = self.login(ADMIN)
        full = self.get(f"/api/calls/{call['id']}", adm).get_json()
        self.assertGreaterEqual(len(full["turns"]), 8)
        rec = self.get(f"/api/calls/{call['id']}/recording", adm)
        self.assertEqual(rec.status_code, 200)
        self.assertTrue(rec.data.startswith(b"RIFF"))

    def test_failure_scenarios(self):
        self.assertEqual(self.run_scenario("no_answer")["status"], "no_answer")
        self.assertEqual(self.run_scenario("busy")["status"], "busy")
        self.assertEqual(self.run_scenario("network_failure")["status"], "failed")
        flaky = self.run_scenario("stt_flaky")
        self.assertEqual(flaky["status"], "completed")           # retry succeeded
        for sc in ("stt_failure", "llm_timeout"):
            c = self.run_scenario(sc)
            self.assertEqual((c["status"], c["handover"]), ("transferred", 1), sc)
            self.assertGreaterEqual(c["errors"], 1)
        self.assertEqual(self.run_scenario("handover")["status"], "transferred")

    def test_multilingual(self):
        for i in range(3):
            c = self.run_scenario("normal", i)
            self.assertEqual(c["status"], "completed")
            self.assertIn("booking", c["summary"])

    def test_live_call_step_by_step(self):
        adm = self.login(ADMIN)
        a = [a for a in self.get("/api/agents", adm).get_json()["items"] if a["status"] == "deployed"][0]
        cid = self.post("/api/calls/start", adm, {"agent_id": a["id"]}).get_json()["id"]
        self.assertIn(cid, [k["id"] for k in self.get("/api/calls/live", adm).get_json()["items"]])
        self.post(f"/api/calls/{cid}/step", adm, {"text": "What is the price?"})
        done = self.post(f"/api/calls/{cid}/end", adm).get_json()
        self.assertEqual(done["status"], "completed")
        self.assertEqual(self.post(f"/api/calls/{cid}/step", adm, {"text": "hi"}).status_code, 409)


class TestBillingAndMisc(Base):
    def test_invoice_math_and_issue(self):
        adm = self.login(ADMIN)
        self.assertEqual(self.post("/api/billing/generate", adm, {"period": "2026-01"}).status_code, 201)
        inv = [i for i in self.get("/api/billing/invoices", adm).get_json()["items"] if i["period"] == "2026-01"][0]
        self.assertEqual(inv["total"], round(inv["subscription_fee"] + inv["overage_minutes"] * inv["per_minute_rate"], 2))
        self.assertEqual(self.post(f"/api/billing/invoices/{inv['id']}/status", adm, {"status": "issued"}).status_code, 200)
        self.assertEqual(self.post("/api/billing/generate", adm, {"period": "bad"}).status_code, 400)

    def test_tickets_and_notifications(self):
        cl, adm = self.login(SUN), self.login(ADMIN)
        t = self.post("/api/tickets", cl, {"subject": "Help", "body": "Please"}).get_json()
        self.assertEqual(self.post("/api/tickets", adm, {"subject": "x", "body": "y"}).status_code, 403)
        self.c.patch(f"/api/tickets/{t['id']}", headers=adm, json={"status": "resolved", "response": "Done"})
        self.assertGreater(self.get("/api/notifications", cl).get_json()["unread"], 0)

    def test_audit_and_suspension(self):
        adm = self.login(ADMIN)
        self.assertTrue(self.get("/api/audit", adm).get_json()["items"])
        co = self.post("/api/companies", adm, {"name": "Temp Co"}).get_json()
        self.post("/api/users", adm, {"name": "T", "email": "t@temp.local", "password": "longenough1", "company_id": co["id"]})
        h = self.login(("t@temp.local", "longenough1"))
        self.c.patch(f"/api/companies/{co['id']}", headers=adm, json={"status": "suspended"})
        self.assertEqual(self.get("/api/agents", h).status_code, 403)

    def test_security_headers_and_frontend(self):
        r = self.c.get("/api/health")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertEqual(self.c.get("/api/nope").status_code, 404)

    def test_migrations_idempotent(self):
        with self.app.app_context():
            self.assertEqual(db.run_migrations(), [])


if __name__ == "__main__":
    unittest.main()
