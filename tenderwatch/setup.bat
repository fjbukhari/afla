@echo off
rem One-time setup on Windows. Needs Python 3.10 or newer from python.org (tick "Add python.exe to PATH").
cd /d "%~dp0"
py -3 -m venv .venv || python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if not exist config\settings.yaml copy config\settings.example.yaml config\settings.yaml
echo.
echo Setup finished. Next: run.bat (collect tenders), then dashboard.bat (view them).
pause
