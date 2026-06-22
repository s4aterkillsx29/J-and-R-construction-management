JRC Construction Manager v6.3 - Local Login + Host Repair Edition

This version focuses on the issue reported by Jacob: local host did not verify and the login screen needed to appear first, separately from dashboard.

Main changes:
- Start Center now has Open Login and Open Dashboard as separate actions.
- Open Login starts/verifies the local web app and opens /login first.
- Dashboard opens only after login; if not signed in, the app redirects to Login.
- Local host startup verifies /login first before requiring mobile endpoint checks.
- If mobile endpoints fail but login works, the app tells you Login is ready and mobile needs attention.
- Default admin/admin account is created on first setup and repaired if missing/inactive/wrong role.
- Added Host Login Verify tool and reports.

Important:
- Installer does not collect passwords. Login happens inside the secured app.
- Default first setup login is admin/admin. Change it after setup.
- Remote users when your PC is off still require cloud/tunnel/VPN hosting.
