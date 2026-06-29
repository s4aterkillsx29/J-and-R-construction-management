# J & R Construction Manager — Agent Instructions

Jacob Cosentino / J & R Construction. This repo is business management software (jobs, payroll, bookkeeping, mobile field access) — not a generic web app.

## Business context

- **Owner:** Jacob Cosentino — sole proprietor, Ocean Isle Beach / Shallotte NC area
- **Phone:** (910) 712-0936
- **Typical work:** residential decks, fences, stairs, exterior/demo, helper pay, cash/check jobs
- **Customers:** track by name + address (e.g. `403 East 2nd / Jackie`, `315 Sassafras Lane / Lily`)

## What this app does

- **Desktop (PC):** Start Center → Open Office — jobs, invoices, payroll, bookkeeping, files
- **Phone (operations):** Flask host `/mobile` — jobs, pipeline, files, expenses (owner login). Not Cursor — that's for code changes.
- **Phone (Cursor):** Cloud agents edit this GitHub repo; Jacob reviews PRs from phone

## Key paths

| Area | Path |
|------|------|
| Main web server | `app/network_server.py` |
| Localhost foundation | `app/live_server.py` |
| Desktop app | `app/jr_job_manager.py` |
| Mobile companion docs | `mobile_companion/` |
| iPhone setup | `iphone_files/OPEN_ON_IPHONE.txt`, `/mobile/setup` |
| Cloud deploy | `cloud_hosting/` |
| Field work log scripts | `app/log_jackie_*.py` (idempotent DB writers) |
| Evidence / receipts | `evidence/` |
| Database (local, gitignored) | `data/jr_business.db` |

## Mobile routes (business app)

- `/connect` — connection test (public)
- `/mobile/setup` — owner phone onboarding (public)
- `/mobile` — mobile dashboard (login required)
- `/mobile/jobs`, `/mobile/pipeline`, `/mobile/files`
- `/payroll`, `/bookkeeping`, `/expenses` — owner/admin on phone when permitted

## Coding rules

1. **Minimize scope** — small focused diffs; match existing Flask/Python style
2. **Never commit** `.db`, `.env`, passwords, payroll CSVs, tax files, customer PII exports
3. **Idempotent log scripts** — field updates use `app/log_*.py` pattern; safe to re-run
4. **Branch naming** — `cursor/<descriptive-name>-59da`
5. **Owner labor** — job-costing at $30/hr; not deductible owner wage
6. **Helper default** — $140/day; half-day often $120
7. **Customer copies** — exclude internal cost sheets, helper pay notes, tax/profit notes

## Cloud agent setup

```bash
pip install -r requirements.txt
python3 -m unittest tests.test_jrc_smoke -q
```

Optional field log (creates local `data/jr_business.db`):

```bash
python3 app/log_jackie_deck_rebuild_2026-06-29.py
```

## Common phone-agent tasks Jacob requests

- Log field work (job progress, helper pay, owner labor, materials, banking transfers)
- Update job notes / evidence files for active jobs
- Fix mobile UI or `/mobile` routes for iPhone Safari
- Generate customer estimates/invoices (PDF in `docs/quotes/` or `tools/generate_*.py`)
- Sync Dropbox / `iphone_files/` for phone document access

## Privacy

Do not paste live customer SSNs, bank account numbers, or full payroll registers into agent chats. Describe behavior; store details in gitignored DB or Dropbox.
