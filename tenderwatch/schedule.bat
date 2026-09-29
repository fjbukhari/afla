@echo off
rem Creates Windows scheduled tasks that check the portals every day at 07:45 and 14:45.
rem They run while you are signed in to Windows (needed for portals that use your browser sign-in).
cd /d "%~dp0"
schtasks /Create /F /SC DAILY /ST 07:45 /TN "Tender Watch morning" /TR "\"%~dp0run.bat\""
schtasks /Create /F /SC DAILY /ST 14:45 /TN "Tender Watch afternoon" /TR "\"%~dp0run.bat\""
echo.
echo Scheduled. To remove:  schtasks /Delete /TN "Tender Watch morning" /F   (and the same for "Tender Watch afternoon")
pause
