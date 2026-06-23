# JRC Localhost Live Foundation QA

Version: v7.2.0 Localhost Live Foundation
Date: 2026-06-22

## Purpose

This release repairs the localhost start path used by the Start Center and gives the program a complete Flask foundation for local and cloud-style hosting.

## Verified locally before commit

- Python syntax compile completed for the new Flask server module.
- Local Flask server started from the module entrypoint pattern used by the Start Center.
- `GET /api/health` returned `ok: true` with app/version/db/port fields.
- `GET /login` returned the J & R Construction Manager login page.
- First setup login `admin` / `admin` created an authenticated session.
- Authenticated `GET /api/jobs` returned seeded job data, including the 403 East 2nd active job record.

## Main routes/components included

- `/login` and `/logout`
- `/dashboard`
- `/jobs`, `/jobs/new`, `/jobs/<id>`
- `/customers`, `/customers/new`
- `/documents`, `/documents/new`
- `/expenses`
- `/payroll`
- `/files`
- `/reports`
- `/admin`
- `/mobile`
- `/connect`
- `/register`
- `/apply`
- `/api/health`
- `/api/connection`
- `/mobile/ping`
- `/api/jobs`
- `/api/export/jobs.csv`

## Startup paths

- Start Center continues to call `python -m app.network_server`.
- `app/network_server.py` now imports and runs `app.live_server`.
- `START_LOCAL_SERVER.bat` starts the local server and opens `/login`.
- `Procfile` supports cloud hosts using `gunicorn app.network_server:app`.

## First setup

Default local setup login remains:

- Username: `admin`
- Password: `admin`

The admin page should be used to change the password before any real cloud/public use.
