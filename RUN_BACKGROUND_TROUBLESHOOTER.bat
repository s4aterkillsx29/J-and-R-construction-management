@echo off
setlocal
cd /d "%~dp0"
title JRC Background Troubleshooter
call "%~dp0ensure_venv.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m app.background_troubleshooter
pause
