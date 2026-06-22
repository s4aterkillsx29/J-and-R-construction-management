JRC Construction Manager v7.1 - Primary Live Reliable Business Edition

This is the recommended final live direction for J & R Construction.

Best server choice for your business:
- Use Render paid Web Service + Persistent Disk for the simplest reliable live setup.
- Use Railway or Fly.io only if you prefer those dashboards and understand volumes/databases.
- Use Cloudflare Tunnel only as a safer self-host fallback.
- Do not use direct router port forwarding to a home laptop as the primary business server.

Why this structure:
- Customers, workers, managers, and non-company users need an HTTPS URL that stays on.
- Your laptop can sleep, reboot, move networks, or be blocked by Windows Firewall.
- A cloud service gives logs, health checks, restart behavior, persistent storage, and easier public access.

Critical setup before sharing links:
1. Set JRC_SECRET_KEY.
2. Set JRC_INITIAL_ADMIN_PASSWORD.
3. Set JRC_TRUSTED_HOSTS.
4. Set JRC_CLOUD_BASE_URL.
5. Confirm /api/live/ready passes.
6. Change owner/admin password after first login.
7. Run Primary Live Server Check.
8. Run Admin Security Final Check.
9. Run Customer Request Final Check.
10. Confirm customers only see their own customer portal/request pages.
