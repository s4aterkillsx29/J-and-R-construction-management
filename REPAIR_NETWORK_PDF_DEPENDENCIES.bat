@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m app.dependency_tools
) else (
  python -m app.dependency_tools
)
pause
