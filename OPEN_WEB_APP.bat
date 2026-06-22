@echo off
setlocal
cd /d "%~dp0"
title J and R Construction Manager - Web UI
call "%~dp0ensure_venv.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m app.runtime_utils
exit /b %errorlevel%
