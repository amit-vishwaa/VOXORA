@echo off
REM DELETES the local database and recordings, then loads fresh sample data.
cd /d "%~dp0"
call backend\.venv\Scripts\activate.bat
cd backend
python manage.py reset
pause
