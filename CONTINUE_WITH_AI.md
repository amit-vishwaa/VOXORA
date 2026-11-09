# Continuing with another AI coding assistant (Antigravity, Codex, etc.)

**Prompt to paste first:** “Read CONTINUE_WITH_AI.md, DEVELOPMENT_STATUS.md and PROJECT_DOCUMENTATION.md. Do not rewrite existing modules; make the smallest change that achieves the task, keep all tests green, and update DEVELOPMENT_STATUS.md.”

## Overview
Flask JSON API + static vanilla-JS SPA, SQLite, SQL migrations, provider adapters. Start: `cd backend && python manage.py run` (http://127.0.0.1:5000). Install: `pip install -r backend/requirements.txt`.
## Where things are
- `backend/app/__init__.py` app factory, error handlers, security headers, static serving
- `backend/app/security.py` **auth + tenant isolation — every new route must use `auth_required` and `company_scope()/get_owned()`**
- `backend/app/db.py` SQL helpers (`query`, `execute`), `audit()`, `notify_*()`, migration runner
- `backend/app/engine/orchestrator.py` call pipeline; `engine/providers/` interfaces (`base.py`), mocks, stubs, registry
- `backend/app/routes/*.py` API; `backend/migrations/*.sql` schema; `backend/app/seed.py` sample data
- `frontend/core.js` (escaping template `h\`\``, api(), charts), `views.js` (screens), `main.js` (router/events)
## Conventions
- Schema change = **new** migration file `00N_name.sql`; never edit applied ones.
- SQL always parameterised. Return JSON `{error: "..."}` via `fail(msg, status)`.
- Clients get 404 for foreign rows. Add a test for any new tenant-owned resource (see `TestRolesAndIsolation`).
- Frontend: no inline JS/handlers (CSP); use `data-act` / `data-form`; interpolate through `h\`\`` so text is escaped; wrap trusted HTML with `raw()` only.
- Keep mocks deterministic. Don't present simulated output as real.
## Preserve
Tenant isolation, approval workflow rules, audit logging, redacted client views, test suite, no-secrets-in-code.
## Known problems / priorities
See `DEVELOPMENT_STATUS.md` (missing + blockers). Suggested order: browser check of UI → real LLM adapter → E2E tests → streaming STT/TTS → telephony → PostgreSQL → email/payments.
## Add a real provider
1. Implement the interface in `engine/providers/base.py` (e.g. `class OpenAILLM(LLMProvider)`), set `simulated=False, implemented=True`.
2. Register in `REGISTRY` in `providers/__init__.py`. 3. Read keys from env only. 4. Raise `ProviderError` on timeouts so retry/handover works. 5. Add a test with the HTTP call mocked.
## Test commands
`cd backend && python -m unittest discover -s tests -v` (or `pytest`). Reset sample data: `python manage.py reset`.
## Avoid
Rewriting to another framework, adding heavy dependencies without need, changing API response shapes the frontend uses, removing mock providers (tests rely on them).
