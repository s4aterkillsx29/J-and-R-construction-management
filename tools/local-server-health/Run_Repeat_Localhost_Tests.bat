@echo off
setlocal
cd /d "%~dp0\..\.."
echo Running J&R Construction Manager repeat localhost health tests...
python tools\local-server-health\test_local_server_health_repeat.py
set EXITCODE=%ERRORLEVEL%
echo.
if "%EXITCODE%"=="0" (
  echo PASS - Localhost health repeat tests passed.
) else (
  echo FAIL - Localhost health repeat tests failed.
)
pause
exit /b %EXITCODE%
