@echo off
title Biodynamic Gardening Calendar
cd /d "%~dp0"

rem ---- find Python ----
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
rem the Windows "python" placeholder only opens the Microsoft Store - make sure Python really runs
if defined PY ( %PY% -c "import sys" >nul 2>nul || set "PY=" )
if not defined PY goto :nopython

rem ---- first run: create a private Python environment inside this folder ----
if exist ".venv\Scripts\python.exe" goto :ready
echo.
echo  First-time setup: installing the app's components.
echo  This needs an internet connection and takes about 2 to 5 minutes. Please wait...
echo.
%PY% -m venv .venv || goto :fail
".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
echo.
echo  Setup finished.

:ready
rem ---- open the app in its own window (Microsoft Edge "app" window, no tabs or address bar) ----
rem      if Edge is not found, the usual web browser opens instead
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" goto :browser
start "" /min cmd /c "ping -n 7 127.0.0.1 >nul & start "" "%EDGE%" --app=http://localhost:8502 --window-size=1360,960"
goto :run
:browser
start "" /min cmd /c "ping -n 7 127.0.0.1 >nul & start http://localhost:8502"

:run
echo.
echo  Starting the app. Its window opens in a few seconds (address: http://localhost:8502).
echo  KEEP THIS BLACK WINDOW OPEN (it may be minimised on the taskbar) while you use the app.
echo  To stop the app completely, close this black window.
echo.
".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8502
pause
exit /b 0

:nopython
echo.
echo  Python was not found on this computer.
echo  Please install it from https://www.python.org/downloads/
echo  and tick "Add python.exe to PATH" on the first installer screen.
echo.
start "" https://www.python.org/downloads/
pause
exit /b 1

:fail
echo.
echo  Setup did not complete. Check your internet connection, then double-click
echo  "Start app.bat" again. If it keeps failing, delete the ".venv" folder inside
echo  this folder and try once more.
echo.
if exist ".venv" rmdir /s /q ".venv"
pause
exit /b 1
