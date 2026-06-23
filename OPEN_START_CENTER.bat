@echo off
setlocal
set "LIVE=%LOCALAPPDATA%\J_and_R_Construction_Manager"
if not exist "%LIVE%\app\start_center.py" set "LIVE=%~dp0"
cd /d "%LIVE%"

call "%LIVE%\ensure_venv.bat" >nul 2>&1
if exist "%LIVE%\.venv\Scripts\python.exe" (
  "%LIVE%\.venv\Scripts\python.exe" -m app.process_lifecycle >nul 2>&1
)

echo Closing any old J and R windows...
for /f "tokens=2 delims=," %%a in ('wmic process where "CommandLine like '%%start_center.py%%'" get ProcessId /format:csv 2^>nul ^| find /v "Node"') do taskkill /PID %%a /F >nul 2>&1
ping -n 2 127.0.0.1 >nul

echo Opening Start Center...
start "J and R Construction Manager" /D "%LIVE%" "%LIVE%\.venv\Scripts\python.exe" "%LIVE%\app\start_center.py"
