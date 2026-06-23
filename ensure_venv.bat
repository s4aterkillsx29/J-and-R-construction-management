@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" exit /b 0

echo.
echo Virtual environment not found. Setting up Python environment...
echo.

where py >nul 2>&1
if %errorlevel%==0 (
  py -3 -m venv .venv
) else (
  where python >nul 2>&1
  if %errorlevel%==0 (
    python -m venv .venv
  ) else (
    echo Python 3 was not found. Install from https://www.python.org/downloads/windows/
    echo Enable "Add python.exe to PATH" during install, then run this again.
    exit /b 1
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo Failed to create .venv. Check that Python 3.11+ is installed.
  exit /b 1
)

if not exist "requirements.txt" (
  echo requirements.txt not found in %~dp0
  exit /b 1
)

echo Installing dependencies from requirements.txt...
".venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check --no-input --no-warn-script-location --default-timeout 120
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --no-input --no-warn-script-location --default-timeout 120 -r requirements.txt
if errorlevel 1 (
  echo Dependency install failed. See logs above.
  exit /b 1
)

echo.
echo Virtual environment ready.
exit /b 0
