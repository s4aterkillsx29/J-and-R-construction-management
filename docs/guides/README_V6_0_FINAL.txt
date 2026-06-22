J & R Construction Manager v6.0 Complete Final Business Cloud Edition

Purpose:
- Local/offline office operation for Jacob and J & R Construction.
- Cloud/tunnel/VPS-ready access for managers, workers, customers, and non-company users.
- Customer portal and job requests are separate from internal records.
- Dropbox/local folders are used as file-source/evidence storage, not as a live shared database.

Installer behavior:
- Preserves data, evidence, exports, backups, logs, business standards, file sources, uploads, and ChatGPT imports.
- Does not collect or store passwords inside the installer.
- Opens the secured First Setup/Login handoff after install.

Security model:
- Login decides the dashboard perspective.
- Remembered device is opt-in only and expires after 90 days.
- Admin/manager/customer/non-company/worker/viewer dashboards are separated by role permissions.
- Public/internet use should run through HTTPS cloud hosting or Cloudflare Tunnel/VPN, not an exposed laptop/router.

After install:
1. Login.
2. Change admin/admin if still active.
3. Run Self Setup + Verify.
4. Run v6 Final Readiness.
5. Set Cloud Access only when a real hosted/tunnel URL exists.
