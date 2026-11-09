# Project Documentation

## 1. Architecture
```
Browser (static SPA: index.html + core/views/main.js)
   │  JSON over HTTPS, Authorization: Bearer <JWT>
Flask app (backend/app)  ── routes/* ──►  security.py (auth, roles, tenant scope)
   │                                 └─►  engine/orchestrator.py ─► providers (STT, LLM, TTS, telephony)
SQLite (backend/instance/voxora.db) + recordings/*.wav
```
Single deployable: Flask also serves the frontend. No build step. Providers are swappable through `engine/providers/__init__.py` (REGISTRY). Each agent stores which provider name it uses per slot.

## 2. Roles & isolation
- `super_admin`: no company; full control. `client`: bound to one company.
- `security.auth_required(*roles)` re-reads user and company status from the DB on every request (disabling a user or suspending a company takes effect immediately).
- `company_scope()` forces clients onto their own company and ignores any `company_id` they send. `get_owned()` returns **404** (not 403) for other tenants' rows. Clients never see test calls, draft invoices, prompts, provider settings or version history.
- Verified by automated tests (cross-tenant agent/call/recording access, redacted views, read-only enforcement, scoped analytics/billing).

## 3. Modules
| Module | File | Notes |
|---|---|---|
| Auth | routes/auth.py | login, lockout (5 fails → 5 min), change password |
| Companies/Users/Audit/Meta | routes/admin.py | admin only (meta for all) |
| Agents & workflow | routes/agents.py | CRUD, versions, knowledge, test, approval, deploy, rollback |
| Calls | routes/calls.py | history, detail, recording, live, simulate/start/step/end |
| Analytics, Billing, Notifications, Tickets | routes/business.py | |
| Voice engine | engine/orchestrator.py | start_call → handle_utterance → end_call, simulate_call |
| Providers | engine/providers/ | base.py interfaces, mock.py (simulated), stubs.py (NOT implemented real adapters) |

## 4. Agent lifecycle
`draft → testing → pending_approval → approved → deployed`; `rejected` returns to approval after changes.
Rules: request-approval needs ≥1 completed test call on the **current version**; only the agent's company (or a super admin) can approve/reject; only `approved` can be deployed; only `deployed` agents take non-test calls; **editing** creates a new version and drops approved/deployed agents back to `testing`; **rollback** copies an old version's config into a new version and redeploys immediately (emergency path, audited, skips approval).

## 5. Call pipeline & failure handling
Telephony `place_call` → greeting TTS → per caller line: STT (retry once) → LLM (retry once) → TTS. Persistent STT/LLM failure → apology + **handover** (status `transferred`, mock SIP transfer to the agent's handover number). Scenarios: `normal, no_answer, busy, network_failure, stt_flaky, stt_failure, llm_flaky, llm_timeout, handover`. Duration = simulated speech+latency time (not wall-clock). Billable minutes = ceil(duration/60), only non-test calls.

## 6. Database (migrations/001_init.sql)
`plans, companies, users, agents, agent_versions, knowledge_docs, approvals, calls, call_turns, invoices, notifications, tickets, audit_logs` (+ `schema_migrations`). Dates are UTC text `YYYY-MM-DD HH:MM:SS`. Foreign keys enforced. Index on `calls(company_id, started_at)`.

## 7. API overview (all under /api, JSON)
| Method & path | Who | Purpose |
|---|---|---|
| POST /auth/login · GET /auth/me · POST /auth/change-password | all | session |
| GET /meta | all | industries, languages, voices, plans, scenarios (+providers for admin) |
| GET/POST /companies · PATCH /companies/:id | admin | |
| GET/POST /users · PATCH /users/:id | admin | |
| GET /agents · GET /agents/:id | all (scoped, redacted for clients) | |
| POST /agents · PATCH /agents/:id | admin | PATCH makes a new version |
| GET /agents/:id/versions · GET/POST /agents/:id/knowledge · DELETE /knowledge/:id | admin | |
| POST /agents/:id/test-call · /request-approval · /deploy · /rollback | admin | |
| POST /agents/:id/approve · /reject | client of that company or admin | |
| GET /calls (filters: status, direction, agent_id, q, test) · GET /calls/live · GET /calls/:id · GET /calls/:id/recording | all (scoped) | |
| POST /calls/simulate · /calls/start · /calls/:id/step · /calls/:id/end | admin | |
| GET /analytics/overview?days=&company_id= | all (scoped) | |
| GET /billing/invoices · GET /billing/usage | all (scoped; clients see issued/paid only) | |
| POST /billing/generate · POST /billing/invoices/:id/status | admin | |
| GET /notifications · POST /notifications/read | all | |
| GET/POST /tickets (POST client only) · PATCH /tickets/:id (admin) | | |
| GET /audit | admin | |
| GET /health | public | |

## 8. Security measures
Hashed passwords (Werkzeug scrypt/pbkdf2), JWT HS256 with expiry, secret never in code (env or generated file), login lockout, parameterised SQL everywhere, input validation, JSON-only API, security headers + CSP (no inline scripts), automatic HTML-escaping in the frontend template helper, recording path-traversal guard, 1 MB request cap, audit trail. **Not done:** MFA, refresh/revocation list, rate limiting beyond login, CSRF not needed (bearer token, not cookies) but the token lives in sessionStorage.

## 9. Key decisions
- **Flask + SQLite + vanilla JS** instead of a heavier stack: zero install friction on an 8 GB laptop, no Node toolchain, fully testable offline. Trade-off: SQLite is single-node; vanilla JS UI has no component framework.
- Plain SQL migrations instead of an ORM: simple, explicit; port to PostgreSQL later.
- Mock providers are deterministic (hash-based jitter) so tests are stable.
