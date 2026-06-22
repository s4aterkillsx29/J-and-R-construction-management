JRC Construction Manager v7.1 - Cloud Primary Live Business Edition

This package keeps the J&R desktop/installer tools, but the recommended live system is cloud-first:
- Cloud host runs the app 24/7 using Gunicorn.
- Database and program data use JRC_DATA_DIR on persistent cloud storage.
- First owner login on cloud must use JRC_INITIAL_ADMIN_PASSWORD.
- Do not use admin/admin on public/cloud/customer access.
- Set JRC_SECRET_KEY, JRC_TRUSTED_HOSTS, and JRC_CLOUD_BASE_URL before live use.

After deploy, open /api/health and /api/cloud/primary-status, then run the v7 Cloud Primary Final Check from Tools / Repair.
