@echo off
setlocal
cd /d "%~dp0"
title J and R Construction Manager - Setup OFFICE Laptop
echo.
echo OFFICE LAPTOP SETUP
echo - Cursor + Dropbox office work
echo - Can run host HERE or connect to dedicated host laptop
echo.
set /p REMOTE="Remote host URL (optional, e.g. http://192.168.50.60:8765): "
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m app.host_laptop_roles --profile OwnerMaster --remote-host-url "%REMOTE%"
) else (
  python -m app.host_laptop_roles --profile OwnerMaster --remote-host-url "%REMOTE%"
)
echo.
pause
