@echo off
cd /d "%~dp0"
title J and R Construction Manager Backup
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "app\backup_only.py"
) else (
  python "app\backup_only.py"
)
pause
