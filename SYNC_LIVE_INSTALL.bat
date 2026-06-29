@echo off
setlocal
cd /d "%~dp0"
set "SRC=%~dp0"

rem Owner Master (Desktop) + Worker fallback (AppData)
for %%D in (
  "%USERPROFILE%\Desktop\J and R Construction Manager"
  "%USERPROFILE%\OneDrive\Desktop\J and R Construction Manager"
  "%LOCALAPPDATA%\J_and_R_Construction_Manager"
) do call :SyncOne "%%~D"

echo.
echo Live sync complete for all install locations found.
echo Restart J and R Construction Manager to load v7.8.0.
pause
exit /b 0

:SyncOne
set "DST=%~1"
if not exist "%DST%" (
  echo Skipping missing: %DST%
  exit /b 0
)
echo Syncing to: %DST%
if not exist "%DST%\app" mkdir "%DST%\app"
if not exist "%DST%\scripts" mkdir "%DST%\scripts"
xcopy /E /Y /I "%SRC%app\*.py" "%DST%\app\" >nul
for %%F in (
  ensure_venv.bat
  setup_runtime_env.bat
  install_jr_job_manager_ui.ps1
  Launch-JRC-Manager.bat
  START_NETWORK_SERVER.bat
  RUN_FULL_SYSTEM_CHECK.bat
  RUN_BACKGROUND_TROUBLESHOOTER.bat
  run_jr_manager.bat
  run_jr_manager_hidden.vbs
  run_jr_job_manager.bat
  requirements.txt
  VERSION.txt
  INSTALL_J_AND_R_MANAGER.vbs
  !!! START INSTALL HERE.vbs
  LIVE_FULL_UPDATE.vbs
) do if exist "%SRC%%%F" copy /Y "%SRC%%%F" "%DST%\" >nul
if exist "%SRC%scripts\Ensure-DesktopShortcuts.ps1" copy /Y "%SRC%scripts\Ensure-DesktopShortcuts.ps1" "%DST%\scripts\" >nul
if exist "%SRC%scripts\Seed-OwnerEmergencyKey.ps1" copy /Y "%SRC%scripts\Seed-OwnerEmergencyKey.ps1" "%DST%\scripts\" >nul
if exist "%SRC%assets" xcopy /E /Y /I "%SRC%assets\*" "%DST%\assets\" >nul
exit /b 0
