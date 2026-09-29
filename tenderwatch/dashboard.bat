@echo off
rem Opens the dashboard at http://localhost:8766 . Keep this window open while you use it.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
start "" http://localhost:8766
python -m tw serve %*
