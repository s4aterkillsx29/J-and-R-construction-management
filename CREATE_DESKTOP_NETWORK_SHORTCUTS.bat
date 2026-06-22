@echo off
setlocal
set "APPDIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$W=New-Object -ComObject WScript.Shell; $D=[Environment]::GetFolderPath('Desktop'); $S=$W.CreateShortcut((Join-Path $D 'J and R Construction Manager - Network Server.lnk')); $S.TargetPath=(Join-Path '%APPDIR%' 'START_NETWORK_SERVER.bat'); $S.WorkingDirectory='%APPDIR%'; $S.Save(); $S2=$W.CreateShortcut((Join-Path $D 'J and R Construction Manager - Open Browser.lnk')); $S2.TargetPath=(Join-Path '%APPDIR%' 'OPEN_NETWORK_MANAGER.bat'); $S2.WorkingDirectory='%APPDIR%'; $S2.Save();"
echo Desktop shortcuts created.
pause
