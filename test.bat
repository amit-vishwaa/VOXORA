@echo off
cd /d "%~dp0"
call backend\.venv\Scripts\activate.bat
cd backend
python -m unittest discover -s tests -v
pause
