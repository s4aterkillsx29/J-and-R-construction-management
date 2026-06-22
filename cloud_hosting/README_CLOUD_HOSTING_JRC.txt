J & R CONSTRUCTION MANAGER - CLOUD HOSTING GUIDE v4.9

Purpose
- Local hosting from a Windows laptop can be unreliable for phones outside your Wi-Fi because of firewall, router, NAT, sleep mode, antivirus, and changing IP addresses.
- Cloud hosting makes the mobile/apply/register pages available from other locations through one stable HTTPS URL.

Recommended setup
1. Keep the Windows desktop program for office/admin work.
2. Use a cloud/VPS/tunnel-hosted copy only for mobile access, worker signup, job applications, and owner review.
3. Use HTTPS only.
4. Change admin/admin immediately before remote access.
5. Use strong passwords and admin approval.
6. Keep Dropbox as file/evidence storage, not as a live shared database.
7. Back up before moving or syncing data.

Safer options
- Best simple option: secure tunnel/VPN to this computer for your own use and trusted workers.
- Best business option: small cloud/VPS running Docker with HTTPS, backups, and a domain/subdomain.
- Avoid router port forwarding directly to your laptop unless a professional sets up firewall/HTTPS/security.

Included files
- Dockerfile: container build for the web server.
- docker-compose.yml: local/cloud container runner.
- Procfile: simple platform web start command.
- render.yaml: starter blueprint for supported platforms.
- cloud_entry.py: cloud entry point that starts the J&R Flask app in public-host mode.
- env.example: environment settings to review.

Important limitations
- This package cannot automatically create a paid cloud account or domain for you.
- Cloud hosting may require a monthly cost.
- Do not upload private customer data to an untrusted/free public service without understanding privacy/security.
- If you want the cleanest business-grade setup, use a domain, HTTPS, backups, and admin-only controls.

Quick cloud workflow
1. Install/open the desktop app.
2. Run System Check.
3. Change admin password.
4. Create a backup ZIP from the web app or program folder.
5. Deploy cloud_hosting with app/ and data/ preserved as needed.
6. Set JRC_PUBLIC_HOST_MODE=1 and a strong SECRET_KEY/JRC_SECRET_KEY if your platform supports environment variables.
7. Test /api/health, /connect, /mobile, /register, /apply.
8. Only then share links with workers/customers.
