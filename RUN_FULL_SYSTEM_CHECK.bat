@echo off
setlocal
cd /d "%~dp0"
title J and R Construction Manager - System Check
if not exist .venv\Scripts\python.exe (
  echo Virtual environment missing. Run INSTALL_JR_JOB_MANAGER.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe app\system_check.py
if errorlevel 1 (
  echo.
  echo System check found errors. Review the report saved in the exports folder.
) else (
  echo.
  echo System check passed. Review the report saved in the exports folder.
)
pause
