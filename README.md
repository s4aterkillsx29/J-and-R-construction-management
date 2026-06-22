# J & R Construction Manager

**JRC Construction Manager v7.1.0 — Primary Live Reliable Business Edition**

Construction management software for jobs, payroll, customer portals, hosting, and business operations.

## Quick start

1. Read `00_READ_ME_FIRST_INSTALL.txt` and `START_HERE.txt`
2. Run `!!! START INSTALL HERE.vbs` (or `INSTALL_JR_JOB_MANAGER.bat`)
3. Use the desktop shortcut **J and R Construction Manager** for daily use

## Repository layout

| Path | Purpose |
|------|---------|
| `app/` | Python application source |
| `assets/` | Icons and static assets |
| `cloud_hosting/` | Cloud deployment configs (Render, Railway, Fly.io, Docker) |
| `cloud_templates/` | Nginx, systemd, and backup templates |
| `data/` | Default config JSON (no secrets committed) |
| `docs/qa/` | QA checklists by version |
| `docs/guides/` | Feature guides, troubleshooting, and deployment notes |
| `docs/release-notes/` | Version-specific README files |
| `mobile_companion/` | Mobile access documentation |
| `scripts/` | *(install/run scripts live at repo root — they use relative paths)* |

Root-level `.bat`, `.vbs`, and `.ps1` files are the Windows installer and server launchers.

## Requirements

- Python 3 (see `requirements.txt`: Flask, ReportLab, Waitress, Gunicorn)
- Windows for local install scripts; Docker/Linux for cloud hosting

## Cloud deployment

See `HOSTING_GUIDE.txt`, `cloud_hosting/README_CLOUD_HOSTING.txt`, and `docs/release-notes/README_V7_1_PRIMARY_LIVE_RELIABLE.txt`.

Do **not** commit `.env` files, database files, or private customer exports. Use `cloud_hosting/env.example` as a template.

## Version

See `VERSION.txt` for the current release label.
