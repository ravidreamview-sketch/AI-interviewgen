@echo off
title Ravi GenAI Studio
echo ==============================================
echo   Starting Ravi GenAI Studio
echo ==============================================
echo.

:: Check if virtualenv exists, create if not
if not exist "venv\Scripts\activate.bat" (
    echo [*] Creating virtual environment...
    python -m venv venv
)

:: Activate virtualenv
call venv\Scripts\activate.bat

:: Install dependencies
echo [*] Checking dependencies...
pip install -r requirements.txt --quiet

:: Start local web server
echo.
echo [*] Server starting at: http://127.0.0.1:8000
echo [*] Opening browser...
echo.

start "" "http://127.0.0.1:8000/candidate/login"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

pause
