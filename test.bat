@echo off
rem Windows shortcut: double-click to run the automatic tests.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe python -m venv .venv
call .venv\Scripts\activate
python -m pip install -q -r requirements.txt
python test_synapsehr.py
python test_api.py
pause
