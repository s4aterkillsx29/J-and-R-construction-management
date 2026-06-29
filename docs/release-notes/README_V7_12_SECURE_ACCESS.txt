J and R Construction Manager — v7.12.0
Secure Access & Account Verification Edition
Released: June 28, 2026

Repository: https://github.com/s4aterkillsx29/J-and-R-construction-management

HIGHLIGHTS
----------
- Global login gate: every user (including admin) must sign in before any web page
- Account creation: /register stays Pending until owner/admin approves
- Admin account type changes inline + Full edit with mastery key for Owner/Admin
- File security: payroll/tax/internal costing blocked for worker/helper/customer
- Unified Home Dashboard with role-based tiles
- Densus JRC Admin Hub (/admin/densus) for active sessions and security snapshots
- Live chat, worker applications, customer portal hardening
- Dual-laptop hosting: OwnerMaster vs DedicatedHost profiles
- Easy dedicated host setup: SETUP_DEDICATED_HOST_LAPTOP.bat + START_DEDICATED_HOST_SERVER.bat

DEDICATED HOST LAPTOP (optional 24/7 LAN server)
------------------------------------------------
1. Run SETUP_DEDICATED_HOST_LAPTOP.bat once on the home PC
2. Daily: START_DEDICATED_HOST_SERVER.bat (keep window open)
3. Office PC: Start Center → Connect to Remote Host

NOT INCLUDED IN THIS REPO
-------------------------
- Business records, job folders, tax CSVs, receipts (Dropbox office records only)
- Runtime data/ folder (local DB, sessions, secrets — created at install)
- exports/ verification reports (generated locally)

INSTALL
-------
See 00_READ_ME_FIRST_INSTALL.txt in repo root.
