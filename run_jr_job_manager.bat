@echo off
setlocal
cd /d "%~dp0"
title J and R Construction Manager
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m app.jr_job_manager
) else (
  python -m app.jr_job_manager
)
if errorlevel 1 pause
