# Installation & Run Guide (Windows 11, beginner friendly)

## 1. What you need
- Windows 11, 8 GB RAM is plenty. **No Node.js, Docker or database server is needed.**
- **Python 3.10 or newer** — https://www.python.org/downloads/ . In the installer tick **“Add python.exe to PATH”**. Check: open *Command Prompt* and run `python --version`.
- An internet connection *only* for the one-time `pip install`.

## 2. Easiest way: the helper scripts
1. Unzip `Voxora-AI-Complete-Project.zip` (e.g. to `C:\Voxora`). Avoid paths inside OneDrive if you can.
2. Double-click **`setup.bat`** — creates a virtual environment, installs Flask/PyJWT/Waitress, copies `.env.example` to `.env`, creates the database and loads sample data.
3. Double-click **`start.bat`** — starts the server and opens http://127.0.0.1:5000
4. Stop with **Ctrl+C** in the black window (or close it).
Other scripts: `test.bat` (run tests), `reset-db.bat` (⚠ wipes data, reloads samples).

## 3. Manual way (same thing, typed)
```bat
cd C:\Voxora
python -m venv backend\.venv
backend\.venv\Scripts\activate
pip install -r backend\requirements.txt
copy .env.example .env
cd backend
python manage.py migrate
python manage.py seed
python manage.py run
```
If PowerShell blocks `activate`, use Command Prompt (cmd) or run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## 4. Environment variables (`.env` in the project root)
See `.env.example` — every line is commented. Key ones: `PORT`, `VOXORA_SECRET_KEY` (blank = auto-generated into `backend/instance/secret.key`), `SEED_*` (sample passwords, only used when seeding).
Changing `.env` needs a restart. Changing SEED_* after seeding has no effect: run `reset-db.bat`.

## 5. Database
SQLite file at `backend\instance\voxora.db` (created automatically). Migrations (`backend\migrations\*.sql`) run on every start; run manually with `python manage.py migrate`. Reset: `python manage.py reset`.

## 6. Troubleshooting
| Problem | Fix |
|---|---|
| `'python' is not recognized` | Reinstall Python with “Add to PATH”, or use `py -3` instead of `python`. |
| `pip install` fails / timeout | Check internet/VPN/proxy; retry. |
| `Address already in use` / port 5000 busy | Set `PORT=5050` in `.env` and restart. |
| Login says “Too many failed attempts” | Wait 5 minutes, or `python manage.py reset`. |
| Blank page / old UI | Hard refresh (Ctrl+F5). |
| Sign-in works but pages say “Session expired” | You restarted with a different `VOXORA_SECRET_KEY`; sign in again. |
| `database is locked` | Close other programs using the .db file (DB browsers) and retry. |
| Want to see errors | They print in the black server window. |
