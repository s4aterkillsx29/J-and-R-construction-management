@echo off
setlocal
cd /d "%~dp0"

echo.
echo Checking JRC Python virtual environment...
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Creating .venv...
  where py >nul 2>&1
  if %errorlevel%==0 (
    py -3 -m venv .venv
  ) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
      python -m venv .venv
    ) else (
      echo Python 3 was not found. Install Python 3 and enable Add Python to PATH.
      exit /b 1
    )
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo Failed to create or find .venv. Check that Python 3.11 or newer is installed.
  exit /b 1
)

if not exist "requirements.txt" (
  echo requirements.txt not found in %~dp0
  exit /b 1
)

echo Repairing and updating dependencies from requirements.txt...
".venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check --no-input --no-warn-script-location --default-timeout 120
if errorlevel 1 (
  echo pip upgrade failed.
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install --upgrade --disable-pip-version-check --no-input --no-warn-script-location --default-timeout 120 -r requirements.txt
if errorlevel 1 (
  echo Dependency install or repair failed. See messages above.
  exit /b 1
)

".venv\Scripts\python.exe" -c "import flask, waitress, reportlab; print('Verified required packages')"
if errorlevel 1 (
  echo Dependency verification failed after install or repair.
  exit /b 1
)

echo.
echo Virtual environment ready and dependencies verified.
exit /b 0
