J and R Construction Manager v4.1 Secure Bookkeeping + Filekeeping Automation

J and R Construction Manager v4.0 Secure Bookkeeping + Device Cookies

Advanced update behavior

The v3.3 installer scans these common locations for old installs/copies:
- LocalAppData\J_and_R_Construction_Manager
- LocalAppData\JR_Job_Manager_Pro
- LocalAppData\J_and_R_Job_Manager_Pro
- LocalAppData\JRC_Job_Manager
- Documents\J_and_R_Construction_Manager and similar names

When old copies are found, the installer archives them inside the current install backups folder before removing old program folders. Business data folders are preserved or migrated when safe. Dropbox folders are never deleted or modified by the installer.

The installer deliberately does not run Python, pip, database initialization, or package repairs. That prevents the install process from hanging. First-run setup and repairs happen from the Start Center after install.


New in v4.0: Bookkeeping Control Center, secure remembered-device cookie policy, better filekeeping/receipt warnings, reconciliation runs, and CSV ledger export.


New in v4.1: Filekeeping Control Center, visible bookkeeping/file alerts, summary report export, and stronger session/cookie settings.
