@echo off
setlocal
cd /d "%~dp0"
call "%~dp0ensure_venv.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
echo.
echo Starting J and R Construction Manager Network Server...
echo Leave this window open while other users are connected.
echo.
".venv\Scripts\python.exe" -m app.network_server
pause
