#!/usr/bin/env bash
# macOS/Linux helper: ./start.sh  (first run creates venv, installs deps, seeds data)
set -e
cd "$(dirname "$0")"
[ -d backend/.venv ] || python3 -m venv backend/.venv
. backend/.venv/bin/activate
pip install -q -r backend/requirements.txt
[ -f .env ] || cp .env.example .env
cd backend && python manage.py migrate && python manage.py seed && python manage.py run
