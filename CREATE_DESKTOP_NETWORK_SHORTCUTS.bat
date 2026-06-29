@echo off
echo Legacy network shortcuts are retired.
echo Use Admin Dashboard in the web app for Shared Host, Mobile Links, and Troubleshooting.
echo Desktop shortcuts: "J and R Construction Manager" and "JRC Install or Update" only.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Ensure-DesktopShortcuts.ps1" -InstallDir "%~dp0"
pause
