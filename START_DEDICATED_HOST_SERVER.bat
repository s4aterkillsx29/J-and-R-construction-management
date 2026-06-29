@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title JRC Host Server - RUNNING - DO NOT CLOSE

echo.
echo ============================================================
echo   J and R Construction Manager - LOCAL HOST SERVER
echo   Keep this window OPEN for phones and workers to connect.
echo ============================================================
echo.

set "JRC_PORT=8765"
set "JRC_SESSION_TIMEOUT_MINUTES=120"
set "JRC_PUBLIC_HOST_MODE=0"
set "JRC_DATA_DIR=%~dp0data"

if not exist ".venv\Scripts\python.exe" (
  echo Python not ready. Run SETUP_DEDICATED_HOST_LAPTOP.bat first.
  pause
  exit /b 1
)

if not exist "data\install_profile.json" (
  echo.
  echo FIRST TIME? Run SETUP_DEDICATED_HOST_LAPTOP.bat once before starting.
  echo.
  pause
  exit /b 1
)

echo Starting server on port %JRC_PORT% ...
echo Local admin on this PC: jrc_host / jrc_host
echo Owner from other devices: admin at the LAN URL below
echo.
echo Press Ctrl+C to stop the server.
echo.

".venv\Scripts\python.exe" -m app.network_server
echo.
echo Server stopped.
pause
