@echo off
setlocal
cd /d "%~dp0"
title J and R Construction Manager - Public Host Mode

echo ============================================================
echo  PUBLIC HOST MODE WARNING
echo ============================================================
echo This mode is for use behind HTTPS, VPN, or a secure tunnel.
echo Do NOT port-forward this laptop directly to the public internet.
echo Change admin/admin before using public host mode.
echo.
pause
set JRC_PORT=8765
set JRC_SESSION_TIMEOUT_MINUTES=60
set JRC_PUBLIC_HOST_MODE=1
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m app.network_server
) else (
  py -m app.network_server
)
pause
