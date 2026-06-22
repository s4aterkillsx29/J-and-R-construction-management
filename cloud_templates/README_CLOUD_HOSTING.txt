J and R Construction Manager - Cloud Hosting Options

This package includes templates for a future cloud/VPS deployment.

Immediate recommended host:
- Jacob's administrator laptop on trusted LAN or VPN.
- Use START_LOCAL_LAN_HOST.bat.

Safer remote access options:
1. VPN or secure tunnel to Jacob's laptop/server.
2. Cloud VPS running Docker with HTTPS and firewall rules.
3. Managed container host with HTTPS, environment secrets, backups.

Minimum production rules before outside users:
- Change admin/admin immediately.
- Use HTTPS, not plain HTTP.
- Use a real domain or secure tunnel URL.
- Back up data daily.
- Keep Dropbox as source/evidence storage, not as a live shared database.
- Only admins can manage users and sessions.
- Review Admin > Online Sessions and Troubleshooting regularly.
