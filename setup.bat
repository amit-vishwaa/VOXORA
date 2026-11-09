@echo off
setlocal
REM One-time setup for Windows. Run from any working directory.
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul && set "PY=py -3"
%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/ and enable Add Python to PATH.
    pause
    exit /b 1
)

if not exist "backend\.venv\Scripts\python.exe" (
    %PY% -m venv backend\.venv
    if errorlevel 1 (
        echo Could not create backend\.venv.
        pause
        exit /b 1
    )
)

"backend\.venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo Could not upgrade pip. Check your internet connection and retry.
    pause
    exit /b 1
)
"backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 (
    echo Dependency installation failed. Check your internet connection and retry.
    pause
    exit /b 1
)

if not exist ".env" copy ".env.example" ".env" >nul
if errorlevel 1 (
    echo Could not create .env from .env.example.
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

echo.
echo Setup complete. Start the app with start.bat
pause
