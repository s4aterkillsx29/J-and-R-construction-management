J and R Construction Manager v2.9.3 Installer No-Hang Fix

This build fixes the installer stopping at the line showing the venv python.exe.
Cause: the old installer captured pip output through hidden pipes, which can hang on Windows.
Fix: optional package install now redirects to log files and has a timeout. The install will finish even if optional package install is slow or blocked.

If shared hosting/PDF features do not work after install, run:
REPAIR_NETWORK_PDF_DEPENDENCIES.bat

Main desktop app, database, business standards, evidence indexing, and local records are preserved during update.
