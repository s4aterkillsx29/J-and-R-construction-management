@echo off
setlocal
cd /d "%~dp0"
title J and R Construction Manager - Full System Test Suite

echo.
echo  J and R Construction Manager - System Test Suite
echo  ================================================
echo.
echo  Choose a test level:
echo    1 = Quick     (~2 min)  daily health check
echo    2 = Standard  (~5 min)  recommended - run weekly
echo    3 = Full      (~12 min) before updates or go-live
echo    4 = Standard + live host probe (host must be running)
echo.

set "CHOICE="
set /p CHOICE="Enter 1, 2, 3, or 4 [default 2]: "
if "%CHOICE%"=="" set CHOICE=2

call "%~dp0ensure_venv.bat"
if errorlevel 1 (
  echo Virtual environment setup failed.
  pause
  exit /b 1
)

set "PY=%~dp0.venv\Scripts\python.exe"
set "ARGS="

if "%CHOICE%"=="1" set "ARGS=--quick"
if "%CHOICE%"=="2" set "ARGS=--standard"
if "%CHOICE%"=="3" set "ARGS=--full"
if "%CHOICE%"=="4" set "ARGS=--standard --with-host"

if "%ARGS%"=="" (
  echo Invalid choice. Using Standard.
  set "ARGS=--standard"
)

echo.
echo Running test suite...
echo.

"%PY%" -m app.run_full_system_test_suite %ARGS%
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo Test suite finished. Review SYSTEM_TEST_SUITE_LAST_REPORT.txt in this folder.
) else (
  echo Test suite found problems. Open SYSTEM_TEST_SUITE_LAST_REPORT.txt for details.
  echo See docs\SYSTEM_TEST_SUITE_GUIDE.md for how to fix common failures.
)
echo.
pause
exit /b %RC%
