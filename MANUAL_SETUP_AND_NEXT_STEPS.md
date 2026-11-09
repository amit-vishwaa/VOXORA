# Manual Setup & Next Steps — what YOU must do

## A. Mandatory, immediate (≈10 minutes)
1. **Install Python 3.10+** (python.org, tick “Add to PATH”). Nothing else is required.
2. **Unzip** the project to a short path like `C:\Voxora`.
3. **Edit nothing yet → run `setup.bat`.** (Optional but recommended: before running it, copy `.env.example` to `.env` and change `SEED_ADMIN_PASSWORD`, `SEED_CLIENT_PASSWORD`.)
4. **Start** with `start.bat`; **stop** with Ctrl+C.
5. **Sign in** at http://127.0.0.1:5000
   - Super Admin dashboard: `admin@voxora.local` + your `SEED_ADMIN_PASSWORD`
   - Client dashboard: `client@sunrise.local` (or `client@carefirst.local`, `client@brightpath.local`) + `SEED_CLIENT_PASSWORD`
6. **Change both passwords** in *Settings* and never reuse the sample ones anywhere real.
7. **Test**: run `test.bat` (22 automated tests). Then try the manual walkthrough:
   - As admin: Agents → *New agent* → Test tab → run a test call (try failure scenarios) → *Request client approval*.
   - Sign out, sign in as the client of that company → open the agent → *Approve*.
   - Back as admin → *Deploy* → Calls → *Simulate call* → open the call (transcript, recording, summary) → Billing → *Generate this month*.
   - Confirm the client cannot see other companies' data or edit agents.

## B. Optional, soon
- Put the project in Git (`.gitignore` already excludes secrets and the DB). Back up `backend\instance\`.
- Customise plan prices (table `plans`, migration `001_init.sql` → add a new migration to change them).
- Replace sample companies/agents with your own via the UI.

## C. Future: connecting real services (none are connected now)
Every real integration = implement one adapter class in `backend/app/engine/providers/` and register it in `providers/__init__.py` (stubs already exist). Then pick it per agent in *Agents → Config*.
| Need | Steps you do | Where the code goes |
|---|---|---|
| **LLM** (e.g. OpenAI / Anthropic / Gemini) | Create account, enable billing, create API key, put in `.env` (`OPENAI_API_KEY=`). | `OpenAILLM.respond/summarize` in `stubs.py` (move to its own file). Use the agent's `prompt`, `history`, `knowledge`. |
| **STT** (Deepgram, Google, Azure…; check Hindi/Gujarati support!) | Account + key. Real telephony sends audio streams: you need a streaming (websocket) pipeline. | `DeepgramSTT.transcribe` |
| **TTS** (ElevenLabs, Google, Azure; verify hi/gu voices) | Account + key; map `voice` names to provider voice IDs. | `ElevenLabsTTS.synthesize` (return audio bytes too; extend orchestrator to store them) |
| **Telephony / SIP** (Twilio, Exotel, Plivo, Knowlarity; India needs DLT/TRAI compliance) | Buy numbers, create SIP trunk, set webhook/media-stream URL to your **public HTTPS** server (use a tunnel such as ngrok while testing). | `TwilioTelephony.place_call/transfer` + inbound webhook route |
| **Cloud hosting** | Choose AWS/GCP/Azure/Render/Fly. Use the sample `Dockerfile` (untested). Move SQLite → PostgreSQL, recordings → object storage (S3), set `VOXORA_SECRET_KEY`, serve over HTTPS. | `app/db.py`, `RECORDINGS_DIR` usage |

## D. Before real commercial launch (not done)
Real providers + latency tuning; PostgreSQL + backups; HTTPS/domain; secrets manager; real call recording storage with consent notices; payments (Razorpay/Stripe), GST invoices (PDF); email/SMS notifications & password reset; MFA; rate limiting / WAF; load & security testing (penetration test); privacy policy, DPDP-Act/TRAI compliance review; monitoring (Sentry/Prometheus); CI/CD; legal terms. See `DEVELOPMENT_STATUS.md` → Production blockers.
