J and R Construction Manager v3.2 Installer Fix

This installer was rebuilt to stop the recurring Windows installer hang.

Important change:
- The installer DOES NOT run Python during install anymore.
- It only copies files, preserves business data, creates folders, and creates one shortcut.
- First-run database/device setup and optional network/mobile/PDF repair happen from inside the Start Center after the app opens.

If an older installer is stuck:
1. Restart the PC.
2. Extract this v3.2 package fresh.
3. Run INSTALL_J_AND_R_MANAGER.vbs.
4. Open the one desktop shortcut.
5. Run System Check from the Start Center.

If the desktop shortcut does not open, install Python from python.org and rerun the installer.
