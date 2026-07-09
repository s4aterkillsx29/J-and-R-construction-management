# J & R Construction Manager — System Test Suite Guide

Use this anytime you want to know if the program is healthy — after an update, before sharing access with workers/customers, or when something feels broken.

---

## Fastest way to run (double-click)

1. Open your JRC install folder
2. Double-click **`RUN_SYSTEM_TEST_SUITE.bat`**
3. Pick a level:
   - **1 — Quick** — daily check (~2 min)
   - **2 — Standard** — recommended weekly check (~5 min)
   - **3 — Full** — before go-live or big updates (~12 min)
   - **4 — Standard + host** — same as 2 but also checks if the web host is running
4. Read **`SYSTEM_TEST_SUITE_LAST_REPORT.txt`** in the install folder when it finishes

Green / `[OK]` = good. `[FAIL]` = fix before sharing access. `[WARN]` = often Dropbox or cloud setup — not always a code bug.

---

## Command line (for power users)

Open PowerShell or Command Prompt in the install folder:

```powershell
# Recommended weekly check
.venv\Scripts\python.exe -m app.run_full_system_test_suite

# Quick daily check
.venv\Scripts\python.exe -m app.run_full_system_test_suite --quick

# Everything before go-live
.venv\Scripts\python.exe -m app.run_full_system_test_suite --full

# Also test live host (start host from Start Center first)
.venv\Scripts\python.exe -m app.run_full_system_test_suite --with-host

# Treat warnings as failures (stricter)
.venv\Scripts\python.exe -m app.run_full_system_test_suite --strict
```

---

## What each mode tests

### Quick (`--quick`)

| Stage | What it checks |
|-------|----------------|
| Environment | Required folders, virtual environment |
| Automated tests | Core smoke tests (DB schema, Flask routes, Office AI imports) |
| Database | System check + automatic schema repair |
| Core verify | Final program verify, login/install, UI dashboard |

**Use when:** Something broke today and you want a fast answer.

---

### Standard (default)

Everything in **Quick**, plus:

| Stage | What it checks |
|-------|----------------|
| Core verify | Customer portal, permissions, dashboard roles |
| Security | Admin password workflow, RBAC audit, account requests, file access |
| Office AI | Office AI tools and routes load correctly |
| Cloud & integration | Cloud deploy files, security markers, Dropbox linkage, live release |

**Use when:** Weekly health check on the office PC.

---

### Full (`--full`)

Everything in **Standard**, plus:

| Stage | What it checks |
|-------|----------------|
| Office AI & v8 | Full v8 build verification (all files, routes, verify scripts) |
| Full phase verify | Office records sync, data pipeline, troubleshooter, disk isolation |
| Live host | Probes `http://127.0.0.1:8765/api/health` if host is running |

**Use when:** Before pushing an update to cloud, or before giving customers/workers access.

---

## Where reports are saved

| File | Location |
|------|----------|
| Latest report (easy to find) | `SYSTEM_TEST_SUITE_LAST_REPORT.txt` (install root) |
| Timestamped report | `exports/JRC_Full_System_Test_Suite_YYYYMMDD_HHMMSS.txt` |
| Machine-readable JSON | `exports/JRC_Full_System_Test_Suite_YYYYMMDD_HHMMSS.json` |

---

## How to read results

```
[OK]   — Passed. No action needed.
[WARN] — Passed with a note. Often means Dropbox or cloud env is not configured yet.
[FAIL] — Must fix. Do not share LAN/cloud access until resolved.
```

**Overall lines:**
- `PASS` — Good to use locally
- `PASSED WITH WARNINGS` — Core app OK; finish Dropbox/cloud setup
- `NEEDS ATTENTION` — Fix `[FAIL]` items first

---

## Common failures and fixes

### `dropbox-records not found` (WARN or FAIL)

**Meaning:** Business records folder is not linked on this PC.

**Fix:**
1. Make sure Dropbox is syncing on this computer
2. Link or copy the business `dropbox-records` folder into the project (or set `JRC_DROPBOX_RECORDS` env var)
3. Confirm this file exists: `dropbox-records/08_Admin_Standards/JRC_JOB_RELATION_REGISTER.csv`
4. Re-run the test suite

---

### `Default/temporary admin password still needs to be changed` (WARN)

**Meaning:** First-setup password `admin / ivygrows` is still active.

**Fix:**
1. Open **Start Center** → **Local Login Gate** (or sign in on localhost)
2. Change the owner password immediately
3. Re-run system check

**Do not share LAN or cloud access until this is done.**

---

### `Live host health probe` — host not running (WARN)

**Meaning:** The shared web server is not started.

**Fix:**
1. Open **Start Center**
2. Click **Start Host** (or **Start Best Host Server**)
3. Re-run with `--with-host` or option 4 in the batch file

---

### `Automated tests (pytest)` FAIL — schema / database

**Meaning:** Desktop app and web server database columns may be out of sync.

**Fix:**
1. Close all JRC windows
2. Run: `.venv\Scripts\python.exe -m app.system_check`
3. If still failing, run: `.venv\Scripts\python.exe -m app.db_health --all`
4. Re-run test suite

---

### `Cloud deploy check` warnings about env vars (WARN)

**Meaning:** Normal on a local office PC. Cloud variables are set on Render/Railway, not locally.

**Fix:** Only action needed when deploying to cloud — see `cloud_hosting/env.example`.

---

## When to run which mode

| Situation | Mode |
|-----------|------|
| App won't open / daily sanity check | Quick |
| Normal weekly maintenance | Standard |
| After git pull or program update | Standard or Full |
| Before cloud deploy or customer access | Full |
| Phone can't reach LAN host | Standard + `--with-host` |

---

## Relationship to other tools

| Tool | Purpose |
|------|---------|
| `RUN_SYSTEM_TEST_SUITE.bat` | **This guide** — one-stop full system test |
| `RUN_FULL_SYSTEM_CHECK.bat` | Database + schema check only (subset) |
| Start Center → Self Setup + Verify | Older multi-script runner |
| `python -m app.v8_build_verify` | Developer release gate only |
| `python -m app.run_phase_verification` | Deep phase audit (included in Full mode) |

**Recommendation:** Use **`RUN_SYSTEM_TEST_SUITE.bat`** as your main “is everything OK?” tool. Use **Full** before go-live.

---

## Remaining known issues (not test bugs)

See `docs/PRODUCTION_READINESS_AUDIT_REMAINING.md` for items that require Jacob's Dropbox setup, password change, or cloud deployment — not code fixes.

---

## Need help?

1. Send `SYSTEM_TEST_SUITE_LAST_REPORT.txt` to whoever helps with IT
2. Check `exports/` for detailed per-script reports
3. Use Start Center → **Auto Repair Host** for common host issues
4. Use Start Center → **Troubleshooter** for guided diagnostics
