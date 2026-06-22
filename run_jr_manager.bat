@echo off
setlocal
cd /d "%~dp0"
if exist "run_jr_manager_hidden.vbs" (
  wscript.exe "%~dp0run_jr_manager_hidden.vbs"
) else if exist ".venv\Scripts\pythonw.exe" (
  ".venv\Scripts\pythonw.exe" "app\start_center.py"
) else (
  python "app\start_center.py"
)
