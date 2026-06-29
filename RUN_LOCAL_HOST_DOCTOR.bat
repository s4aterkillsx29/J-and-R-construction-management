@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m app.host_quick_test
) else (
  py -3 -m app.host_quick_test
)
echo.
echo Host test finished. Check the exports folder for the JSON report.
pause
