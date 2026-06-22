@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Running installer first...
  call INSTALL_JR_JOB_MANAGER.bat
)
echo.
echo Starting J and R Construction Manager Network Server...
echo Leave this window open while other users are connected.
echo.
".venv\Scripts\python.exe" app\network_server.py
pause
