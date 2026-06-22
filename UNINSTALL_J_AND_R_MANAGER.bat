@echo off
setlocal
cd /d "%~dp0"
title Uninstall J and R Construction Manager
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall_jr_manager.ps1"
pause
