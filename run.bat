@echo off
rem Windows shortcut: double-click to set up (first time only) and start SynapseHR.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Setting up for the first time. This takes a minute or two...
  python -m venv .venv
)
call .venv\Scripts\activate
python -m pip install -q -r requirements.txt
echo.
echo Starting SynapseHR. Open http://127.0.0.1:8000 in your browser.
echo Copy a key from the list below to sign in. Press Ctrl+C to stop.
echo.
python -m uvicorn api:app
pause
