@echo off
title Ravi GenAI Studio
echo ==============================================
echo   Starting Ravi GenAI Studio (100%% Free)
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
echo [*] Server is starting at: http://localhost:8000
echo [*] Opening your browser...
echo.

start http://localhost:8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause
