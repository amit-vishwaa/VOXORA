@echo off
setlocal
REM Starts Voxora AI on http://127.0.0.1:5000. Stop with Ctrl+C.
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
    echo Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

"backend\.venv\Scripts\python.exe" -c "import flask, jwt, waitress"
if errorlevel 1 (
    echo Project dependencies are missing. Run setup.bat to install them.
    pause
    exit /b 1
)

"backend\.venv\Scripts\python.exe" backend\manage.py migrate
if errorlevel 1 (
    echo Database migration failed.
    pause
    exit /b 1
)
"backend\.venv\Scripts\python.exe" backend\manage.py seed
if errorlevel 1 (
    echo Sample data setup failed.
    pause
    exit /b 1
)

start "" http://127.0.0.1:5000
"backend\.venv\Scripts\python.exe" backend\manage.py run
pause
