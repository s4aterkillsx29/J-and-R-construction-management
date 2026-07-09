@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title J and R Construction - Dedicated Host ONE-TIME Setup

echo.
echo ============================================================
echo   DEDICATED HOST LAPTOP - ONE-TIME SETUP
echo   (Run this ONCE on the home laptop that will run 24/7)
echo ============================================================
echo.
echo This will:
echo   - Mark this PC as the dedicated host
echo   - Copy your office database (users + chat) if found
echo   - Create jrc_host local admin login
echo   - Put "START JRC Host Server" shortcut on Desktop
echo.

if not exist "ensure_venv.bat" (
  echo ERROR: Run this from the J and R Construction Manager folder.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Setting up Python first time only...
  call "ensure_venv.bat"
)

".venv\Scripts\python.exe" -m app.dedicated_host_easy_setup
if errorlevel 1 (
  echo Setup had errors. See messages above.
  pause
  exit /b 1
)

echo.
echo Creating hostadmin account...
".venv\Scripts\python.exe" -m app.host_account_setup --install-dir "%~dp0" --hostadmin-password "Ivygrows1"

echo.
echo Read DEDICATED_HOST_README.txt in this folder for daily steps.
echo.
if not "%JRC_SETUP_SILENT%"=="1" pause
