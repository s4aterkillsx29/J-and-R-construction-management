# J & R Construction — Cursor Agent Guide (Mobile + Cloud)

This GitHub repo is **application source only**. Business files (quotes, jobs, receipts, payroll, unfinished notes) live in **Dropbox**.

## Mobile access point

Phone Cursor cloud agents on this repo are Jacob's **mobile business access point**.

1. Check Dropbox: `python3 -m app.mobile_cloud_access --status`
2. If credentials exist but mirror empty: `python3 -m app.mobile_cloud_access --bootstrap`
3. Read unfinished work + CURRENT_TO_DO under `dropbox-business/08_Admin_Standards/` (mirrored) before office tasks.
4. Never commit Dropbox business files to GitHub.
5. Prefer DuckDuckGo Desktop on the office PC for Dropbox developer / account web work (never Edge/Chrome for Jacob's accounts).

## Required Cursor secrets (Personal scope)

Set in Cursor → Cloud Agents → Secrets (**Personal**, not Environment):

| Secret | Purpose |
|--------|---------|
| `DROPBOX_REFRESH_TOKEN` | Long-lived Dropbox access (preferred) |
| `DROPBOX_APP_KEY` | Dropbox app key |
| `DROPBOX_APP_SECRET` | Dropbox app secret |
| `DROPBOX_ACCESS_TOKEN` | Short-lived fallback token |

Environment variable (not a secret): `DROPBOX_API_ROOT=/dropbox-records`

After adding secrets, **start a new agent** — existing VMs do not pick up new secrets.

Setup help: `python3 -m app.mobile_cloud_access --setup-help`  
Guide: `docs/guides/MOBILE_CLOUD_CURSOR_ACCESS.txt`

## Office PC alignment

Office PC workspace roots (Windows):

- Business: `C:\Users\enrag\Dropbox\All Files\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22`
- Records: `c:\Users\enrag\projects\JRC-Construction-Office\dropbox-records`

Cloud agents mirror those into `./dropbox-business` via API. Same content, different path.
