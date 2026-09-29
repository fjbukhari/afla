@echo off
rem Reads all portals, then prepares the daily email. The scheduled task runs this file.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
if not exist data mkdir data
python -m tw run %* > data\last-run.log 2>&1
python -m tw digest >> data\last-run.log 2>&1
type data\last-run.log
