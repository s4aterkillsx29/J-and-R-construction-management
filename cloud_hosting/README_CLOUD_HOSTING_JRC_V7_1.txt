JRC Construction Manager v7.1 - Primary Live Reliable Business Edition

Recommended server option for J&R Construction
1. Best practical 24/7 option: Render paid Web Service using Docker + Persistent Disk.
   - Easiest for this Flask/Gunicorn app.
   - Uses healthCheckPath /api/live/ready.
   - Uses persistent disk mounted at /var/data/jrc for database, uploads, evidence, exports, and backups.
2. Alternative: Railway with persistent volume/database service.
3. Alternative: Fly.io with a volume and at least one machine always running.
4. Self-host fallback only: Cloudflare Tunnel. This is safer than router port forwarding because cloudflared makes outbound-only connections.
5. Not recommended for production: direct router port forwarding to a personal laptop. It is fragile and higher risk.

Required live environment variables
JRC_PUBLIC_HOST_MODE=1
JRC_CLOUD_PRIMARY_MODE=1
JRC_DATA_DIR=/var/data/jrc
JRC_SECRET_KEY=<long random secret>
JRC_INITIAL_ADMIN_PASSWORD=<strong first owner password>
JRC_TRUSTED_HOSTS=<your domain or service host>
JRC_CLOUD_BASE_URL=https://<your domain or service host>
JRC_DEVICE_COOKIE_SAMESITE=Lax
JRC_SESSION_TIMEOUT_MINUTES=120

After deployment test these URLs
/api/live/ready
/api/health
/api/cloud/primary-status
/login
/customer/request
/mobile
/register
/apply
/primary-live-readiness

Live data rule
All live production data should live under JRC_DATA_DIR on persistent storage. Do not treat Dropbox as the live database. Dropbox/local file sources remain evidence and document source folders.
