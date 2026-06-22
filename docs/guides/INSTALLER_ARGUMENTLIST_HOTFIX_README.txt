J and R Construction Manager v2.9.4 Installer ArgumentList Hotfix

This version fixes the PowerShell error: "Cannot validate parameter on argument list".

Change made:
- Removed Start-Process -ArgumentList from the optional dependency installer path.
- Uses .NET ProcessStartInfo with a plain argument string instead.
- If optional dependency repair cannot run, the installer continues and logs the issue.
- Business data, database, evidence, exports, backups, ChatGPT imports, Dropbox files, and business standards are preserved.

Install:
1. Extract the ZIP.
2. Open J_and_R_Construction_Manager.
3. Double-click INSTALL_J_AND_R_MANAGER.vbs.
4. Click Install / Update.
