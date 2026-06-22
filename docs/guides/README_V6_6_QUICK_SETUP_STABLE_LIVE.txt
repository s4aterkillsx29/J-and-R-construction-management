JRC Construction Manager v6.6 - Quick Setup Stable Live Edition

Purpose:
- Make installed UI quick and simple.
- Open Quick Setup Login after install without depending on local host.
- Fix first login admin/admin failures caused by legacy password hash versions.
- Preserve changed admin password across future installs/updates.
- Keep customer/remote/cloud users away from default admin access.

First-use steps:
1. Run !!! START INSTALL HERE.vbs.
2. Quick Setup Login opens.
3. For brand-new local first setup only, use admin / admin.
4. Change admin password immediately.
5. Use Open Office or Open Start Center.
6. Use cloud/tunnel URL for outside users; local host is optional testing only.

Security:
- Installer does not collect/store passwords.
- Passwords are handled inside the app database.
- Legacy JRC hashes are accepted once and upgraded after successful login.
- Default admin is blocked from public/cloud/customer-style use.
