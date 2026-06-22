JRC Construction Manager v6.3 - Live Deployment Readiness Edition

This package is the current live-deployment-ready build.

What changed from v6.0:
- Added Live Deployment Readiness checker.
- Added web route /live-deployment-readiness for admin-only verification.
- Added Start Center / Tools button for Live Deployment Readiness.
- Strengthened cloud checklist and deployment structure.
- Updated program labels to v6.3.
- Added final live checklist for owner setup, role testing, cloud variables, and customer/worker links.

Best live structure for J&R:
1. Desktop app: office/admin work, local documents, bookkeeping, payroll/job costing.
2. Cloud/tunnel/VPS app: customers, workers, mobile, applications, shared access.
3. Dropbox/file sources: evidence and document storage, not the live shared SQLite database.
4. HTTPS + JRC_SECRET_KEY + JRC_TRUSTED_HOSTS for real internet use.
5. Separate dashboards for admin, manager, worker, viewer, customer, and non-company/external users.

Run these after install:
- Self Setup + Verify
- System Check
- Permission View Check
- Security Perspective Audit
- Dashboard Role Check
- Live Deployment Readiness
- Cloud Deploy Check
- Internet / Cloud Security Verify
