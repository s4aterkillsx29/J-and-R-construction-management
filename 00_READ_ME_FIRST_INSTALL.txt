J & R Construction Manager v7.6.1 - Admin Dashboard, Host Repair, and Densus Integration

Best install/update order:
1. Extract the ZIP or update the local clone.
2. Run !!! START INSTALL HERE.vbs.
3. Choose **Owner Master PC** — installs to your **Desktop** folder: `J and R Construction Manager`
4. Click Install / Update (migrates old AppData copy to Desktop if needed).
5. Quick Setup Login opens — first-time owner login: ivygrows / ivygrows (this PC only).
6. Change the ivygrows password immediately after first login.
7. Admin → Dropbox Business → Run Dropbox Live Check → Push Sensitive Backup.
8. Run Self Setup + Verify from Start Center.

Security rules:
- ivygrows/ivygrows works only on localhost during first setup — not from phones, LAN, or cloud.
- Restoring ivygrows or other default passwords requires your emergency mastery key.
- Customers and workers cannot access admin controls — role permissions are enforced.
- Dropbox is your sensitive business backup source; the database is backed up into Dropbox, not live-shared.

Data safety: do not commit .env files, database files, local_secrets.env, or customer exports.
