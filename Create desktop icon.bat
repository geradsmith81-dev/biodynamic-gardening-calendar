@echo off
title Create the app icon
cd /d "%~dp0"
echo.
echo  Creating the icon "Biodynamic Gardening Calendar" on your Desktop and in the Start menu...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\make_shortcut.ps1"
if errorlevel 1 goto :fail
echo.
echo  Done. Double-click the new icon on your Desktop to start the app.
echo  To pin it: open the Start menu, find "Biodynamic Gardening Calendar",
echo  right-click it and choose "Pin to Start" or "More" - "Pin to taskbar".
echo  If you move this folder, double-click "Create desktop icon.bat" again.
echo.
pause
exit /b 0
:fail
echo.
echo  The icon could not be created. You can still start the app with "Start app.bat".
echo.
pause
exit /b 1
