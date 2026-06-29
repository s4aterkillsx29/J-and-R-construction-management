@echo off
setlocal
cd /d "%~dp0"

if not exist "logs" mkdir "logs"
set JRC_PORT=8765
set JRC_HOST=0.0.0.0

echo Starting J and R Construction Manager local server...
echo Local login: http://127.0.0.1:%JRC_PORT%/login
echo Connection test: http://127.0.0.1:%JRC_PORT%/connect
echo Health API: http://127.0.0.1:%JRC_PORT%/api/health
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    start "JRC Manager Server" cmd /k py -3 -m app.network_server
) else (
    start "JRC Manager Server" cmd /k python -m app.network_server
)

timeout /t 3 >nul
start "" "http://127.0.0.1:%JRC_PORT%/login"
endlocal
