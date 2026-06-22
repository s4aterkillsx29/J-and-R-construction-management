@echo off
setlocal
cd /d "%~dp0"
title J and R Construction Manager
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "app\jr_job_manager.py"
) else (
  python "app\jr_job_manager.py"
)
if errorlevel 1 pause
