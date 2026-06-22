J & R Construction Manager v6.0 Cloud Hosting Notes

Recommended structure:
- Desktop app remains the local office/admin tool.
- Remote users connect to a hosted HTTPS URL, not to a sleeping laptop.
- Use Render/Railway/Fly.io/Docker VPS or Cloudflare Tunnel.
- Use a persistent database/storage plan before treating cloud as production.
- Set JRC_SECRET_KEY and JRC_TRUSTED_HOSTS in the host environment.
- Set JRC_PUBLIC_HOST_MODE=1 and JRC_CLOUD_BASE_URL=https://your-domain.
- Back up database before every deploy/update.

Role safety:
- Customers: own portal and own requests only.
- Non-company: shared items only.
- Workers/viewers: limited company view.
- Managers/admins: internal office tools by permission.
