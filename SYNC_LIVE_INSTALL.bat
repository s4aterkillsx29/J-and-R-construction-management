@echo off
setlocal
cd /d "%~dp0"
set "SRC=%~dp0"
set "DST=%LOCALAPPDATA%\J_and_R_Construction_Manager"

echo Syncing JRC source to live install folder...
echo   From: %SRC%
echo   To:   %DST%

if not exist "%DST%" mkdir "%DST%"
if not exist "%DST%\app" mkdir "%DST%\app"
if not exist "%DST%\data" mkdir "%DST%\data"
if not exist "%DST%\logs" mkdir "%DST%\logs"

rem Core app code (always overwrite)
xcopy /E /Y /I "%SRC%app\*.py" "%DST%\app\" >nul
if exist "%SRC%app\__pycache__" rmdir /S /Q "%SRC%app\__pycache__" 2>nul
if exist "%DST%\app\__pycache__" rmdir /S /Q "%DST%\app\__pycache__" 2>nul

rem Launchers and setup
for %%F in (
  ensure_venv.bat
  ALLOW_LAN_FIREWALL_ACCESS.bat
  OPEN_START_CENTER.bat
  RESTART_JRC.bat
  OPEN_WEB_APP.bat
  OPEN_NETWORK_MANAGER.bat
  START_NETWORK_SERVER.bat
  RUN_FULL_SYSTEM_CHECK.bat
  run_jr_manager.bat
  run_jr_manager_hidden.vbs
  run_jr_job_manager.bat
  requirements.txt
  VERSION.txt
) do if exist "%SRC%%%F" copy /Y "%SRC%%%F" "%DST%\" >nul

rem Assets
if exist "%SRC%assets" xcopy /E /Y /I "%SRC%assets\*" "%DST%\assets\" >nul

echo.
echo Sync complete. Restart J and R Construction Manager from the desktop shortcut.
echo Tip: close the old window first so Python reloads the updated files.
pause
