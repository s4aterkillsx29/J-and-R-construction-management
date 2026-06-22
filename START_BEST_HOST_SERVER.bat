@echo off
setlocal
cd /d "%~dp0"
title J and R Construction Manager - Best Host Server
set JRC_PORT=8765
set JRC_SESSION_TIMEOUT_MINUTES=120
set JRC_PUBLIC_HOST_MODE=0
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m app.network_server
) else (
  py -m app.network_server
)
pause
