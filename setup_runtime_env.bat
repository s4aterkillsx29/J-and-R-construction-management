@echo off
setlocal
cd /d "%~dp0"
echo.
echo J and R Construction Manager - runtime environment setup
echo.

where py >nul 2>&1
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  set "PY=python"
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Failed to create .venv. Install Python 3.11+ from python.org
    exit /b 1
  )
)

echo Installing/upgrading dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check --no-input --default-timeout 120
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --no-input --default-timeout 120 -r requirements.txt
if errorlevel 1 (
  echo Dependency install failed.
  exit /b 1
)

echo Runtime environment ready.
exit /b 0
