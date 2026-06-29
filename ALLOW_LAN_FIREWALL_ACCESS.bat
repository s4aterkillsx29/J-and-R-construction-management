@echo off
setlocal
cd /d "%~dp0"
TITLE J and R Construction Manager - Allow LAN Firewall Access

net session >nul 2>&1
if errorlevel 1 (
  ECHO Requesting Administrator approval for LAN phone access...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

ECHO ======================================================
ECHO J and R Construction Manager - LAN/Mobile Firewall Fix
ECHO ======================================================
ECHO.
ECHO This opens TCP ports 8765-8779 for trusted private Wi-Fi/VPN.
ECHO Phones and tablets on the same network can then reach the shared host.
ECHO.

call "%~dp0ensure_venv.bat" >nul 2>&1
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" -m app.allow_lan_firewall
) else (
  python -m app.allow_lan_firewall
)

ECHO.
pause
