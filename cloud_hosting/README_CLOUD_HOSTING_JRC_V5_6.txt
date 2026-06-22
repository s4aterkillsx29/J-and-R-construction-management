J & R CONSTRUCTION MANAGER - CLOUD BUSINESS STRUCTURE v5.6

Best practice for J&R:
1. Use the Windows desktop app for office/admin work and local records.
2. Use a separate cloud/tunnel/VPS host for remote users, customers, worker applications, and mobile access.
3. Never depend on a sleeping laptop for outside users.
4. Use HTTPS, a long JRC_SECRET_KEY, and public host mode.
5. Keep customer, worker, viewer, non-company, manager, and admin dashboards role-separated.
6. Back up the data folder before deployment and before updates.

Included deployment choices:
- Docker / VPS: use Dockerfile and docker-compose.yml.
- Render: use render.yaml or create a Python web service with gunicorn.
- Railway: use Dockerfile or the generated railway.json.
- Fly.io: use fly.toml.
- Cloudflare Tunnel: safest way to publish a local or VPS web server without opening inbound router/firewall ports.

Required environment variables for cloud:
JRC_PUBLIC_HOST_MODE=1
JRC_SESSION_TIMEOUT_MINUTES=120
JRC_DEVICE_COOKIE_SAMESITE=Lax
JRC_SECRET_KEY=<long random secret>
JRC_CLOUD_BASE_URL=https://your-domain.example.com

Test after deployment:
/api/health
/api/connection
/api/cloud/status
/connect
/login
/mobile
/register
/apply
/customer/request

Remote-user rule:
Other users can connect when your PC is off ONLY if the cloud/tunnel/VPS server is running. This update makes the program ready for that structure.
