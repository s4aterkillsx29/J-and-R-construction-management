@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set JRC_USE_PROGRAM_SHELL=1
if exist "%~dp0run_jr_manager_hidden.vbs" (
  wscript.exe //nologo "%~dp0run_jr_manager_hidden.vbs"
  exit /b 0
)
if exist ".venv\Scripts\pythonw.exe" (
  start "" /D "%~dp0" ".venv\Scripts\pythonw.exe" -m app.program_shell
  exit /b 0
)
if exist ".venv\Scripts\python.exe" (
  start "" /D "%~dp0" ".venv\Scripts\python.exe" -m app.program_shell
  exit /b 0
)
where pyw >nul 2>&1 && start "" /D "%~dp0" pyw.exe -3 -m app.program_shell && exit /b 0
where py >nul 2>&1 && start "" /D "%~dp0" py.exe -3 -m app.program_shell && exit /b 0
mshta "javascript:var s=new ActiveXObject('WScript.Shell');s.Popup('Python 3 is required. Run JRC Install or Update from your Desktop.',0,'JRC Manager',48);close()"
exit /b 1
