@echo off
setlocal
cd /d "%~dp0"
call "%~dp0ensure_venv.bat" >nul 2>&1
call "%~dp0Launch-JRC-Manager.bat"
