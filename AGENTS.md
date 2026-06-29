# J & R Construction — Agent Instructions (Office Assistant)

Jacob Cosentino / J & R Construction. You are the **office assistant** for jobs, quotes, logging, payroll context, and this Flask business manager repo.

**Read first:** `business_standards/JRC_Active_Jobs_Registry.json` · `business_standards/JRC_Business_Document_Standards.json` · `.cursor/rules/jrc-office-assistant.mdc`

## Critical memory — Lillian Cosentino / 315 Sassafras Lane

| | |
|--|--|
| **Customer** | Lillian Cosentino (Lily) |
| **Address** | 315 Sassafras Lane |
| **Fence job** | **Dog ear fence** — materials from **SW Supply NC** |
| **Job ID** | `JRC-JOB-315-LILLIAN-DOGEAR-FENCE` |
| **NOT this job** | Chain link fence — **never** use chain-link placeholders |

Jacob's **2026-06-29 field cost pad** is synced to cloud (2026-06-30). Internal floor **$8,432.61** — see `docs/internal/lillian-315-sassafras-dogear-fence/INTERNAL_COST_SHEET_LILLIAN_315_DOGEAR_FENCE_20260630.txt`. Customer price **TBD**. Rejected chain-link placeholder ($7,200) does **not** match this scope.

**Also at 315:** Stair set 1 & 2 — $1,000 each invoiced (`INV-JRC-JOB-315-LILY-STAIR-SET-01-001`, `02-001`).

**Rejected/wrong files (ignore):** `tools/generate_lily_315_fence_estimate.py`, chain-link `EST-JRC-JOB-315-LILY-FENCE-001` PDFs — cloud-agent error.

## Other active jobs

- `JRC-JOB-403-JACKIE-DECK-REBUILD` — 403 East 2nd OIB, Jackie

## Business standards (Dropbox + PC Cursor)

- `business_standards/JRC_Business_Document_Standards.json` — document, log, search, customer/internal rules
- `business_standards/JRC_Dropbox_Organization_Standard.txt` — one Dropbox root, folder layout
- `business_standards/JRC_Log_Workflow_Standard.txt` — what "log" means
- `business_standards/JRC_Active_Jobs_Registry.json` — canonical job list for agents

## Office behavior

1. **Search existing files** before new estimates/invoices (Dropbox, evidence, exports)
2. **"Log"** → dated business log + confirmation (`app/log_*.py` pattern for field work)
3. **Customer PDFs** — no internal cost sheets or helper profit notes
4. **Never commit** `.db`, secrets, payroll/tax exports
5. **PC work may be ahead of cloud** — ask Jacob to push or paste when cloud is stale

## App paths

| Area | Path |
|------|------|
| Web server | `app/network_server.py` |
| Desktop Office | `app/jr_job_manager.py` |
| Phone business app | `/mobile`, `/mobile/setup` |
| Field logs | `app/log_*.py` |
| Evidence | `evidence/` |
| Lillian fence record | `docs/internal/lillian-315-sassafras-dogear-fence/` |

## Pay defaults

Owner labor $30/hr job-costing · Helper $140/day · Half-day often $120 · 50/50 deposit terms

## Privacy

No SSNs, bank numbers, or full payroll dumps in chat. Use gitignored DB / Dropbox for live records.
