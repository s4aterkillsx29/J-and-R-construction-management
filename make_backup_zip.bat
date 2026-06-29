@echo off
cd /d "%~dp0"
title J and R Construction Manager Backup
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "-m app.backup_only"
) else (
  python "-m app.backup_only"
)
pause
