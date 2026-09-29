@echo off
rem Shortcut for any command, e.g.   tw login ungm    tw test ppra-fed --show    tw sources
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m tw %*
