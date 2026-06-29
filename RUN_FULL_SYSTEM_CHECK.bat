@echo off
setlocal
cd /d "%~dp0"
title J and R Construction Manager - System Check
call "%~dp0ensure_venv.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m app.system_check
if errorlevel 1 (
  echo.
  echo System check found errors. Review the report saved in the exports folder.
) else (
  echo.
  echo System check passed. Review the report saved in the exports folder.
)
pause
