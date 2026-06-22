JRC Construction Manager v6.3 - Secure Owner Login + Live Final Edition

Purpose:
This release locks down the owner/admin login lifecycle and makes sure customer or outside users cannot use the default admin setup password.

Key behavior:
- Fresh local first setup can use admin / admin only from the local host computer.
- Default admin/admin is blocked from public/cloud/remote/customer-style access.
- Once Jacob changes the admin password, updates preserve the changed password and do not reset it.
- Admin password change requires current password and stronger owner/admin password rules.
- Changing the admin password marks owner setup complete and revokes other active admin sessions.
- If an existing database is missing admin, the program does not recreate admin/admin for remote misuse; owner recovery from trusted local host is required.
- Remembered PC/phone remains opt-in only with 90-day expiration.

Recommended owner setup:
1. Install/update.
2. Open Login first.
3. Log in locally with admin/admin only if this is still first setup.
4. Change the admin password immediately.
5. Run Admin Security Final Check.
6. Run Self Setup + Verify.
7. Do not share customer, worker, or cloud links until default admin is disabled.
