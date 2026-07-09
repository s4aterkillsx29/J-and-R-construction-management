# J & R Construction Manager — Production Audit (Remaining Items)

**Date:** July 8, 2026  
**Branch:** `audit/production-readiness-fixes-2026-07-08`  
**Base version:** 8.1.0 Unified Office Edition  
**Repo:** https://github.com/s4aterkillsx29/J-and-R-construction-management

---

## Fixes Applied on This Branch (smoke-tested)

| Fix | Files changed | Verification |
|-----|---------------|--------------|
| **Workers schema bridge** — `default_rate` ↔ `default_day_rate` | `app/schema_migrations.py` | `tests/test_jrc_smoke.py::test_workers_schema_bridge_after_network_server_init` ✅ |
| **Business log schema bridge** — `timestamp/entry` ↔ `log_time/message` | `app/schema_migrations.py` | Desktop `Database()` opens after web `init_db()` ✅ |
| **Missing Office AI tool** — tax savings plan | `app/office_ai/tools/office_mgmt_check_tax_savings_plan.py` | `office_ai_verification_check` exit 0 ✅ |
| **Missing Office AI tool** — save receipt note | `app/office_ai/tools/save_receipt_note.py` | `tool_registry` import + smoke test ✅ |
| **Security audit script drift (v8)** | `app/admin_security_final_check.py` | exit 0 ✅ |
| **RBAC static audit false positives** | `app/security_perspective_audit.py` | exit 0 ✅ |
| **Removed broken `tools/__init__.py`** | deleted empty/broken init | Office AI imports restored ✅ |

### Test results after fixes

```
pytest tests -q --ignore=tests/test_win11_ui_compat.py
→ 32 passed, 5 subtests passed

app.system_check              → 0 errors
app.admin_security_final_check → 0 errors
app.security_perspective_audit → 0 errors
app.office_ai_verification_check → 0 errors
app.final_program_verify      → 212 passes, 0 errors
app.v8_build_verify           → route smoke 11/11 OK; 2 env errors remain (see below)
```

---

## Still Unfixed — Requires Jacob / Deployment Action

### 1. Dropbox `dropbox-records` workspace not linked (P1)

**Symptom:**
```
[ERROR] dropbox-records not found
ERROR - dropbox_workspace.resolve_dropbox_records
ERROR - office_ai path_security.resolve_office_records
```

**Impact:** Jobs/payroll/income sync between office PC and cloud will not work. Office AI tools that read business records return "not found."

**What Jacob must do:**
1. Sync Dropbox business folder to local machine
2. Create junction/symlink or configure `JRC_DROPBOX_RECORDS` env to point at `dropbox-records`
3. Confirm marker file exists: `08_Admin_Standards/JRC_JOB_RELATION_REGISTER.csv`
4. Re-run `python -m app.live_release_verify` and `python -m app.business_sources_security_audit`

**Not a code bug** — per-business filesystem setup.

---

### 2. Live release verify fails until Dropbox is configured (P1)

`app.live_release_verify` reports 2 errors — same root cause as #1. All live chat/UI checks pass.

---

### 3. Default owner password still active until changed (P1 — security)

System check warns:
```
[WARN] Default/temporary admin password still needs to be changed before sharing access.
```

Default first-setup login is `admin / ivygrows` (localhost only). Remote/LAN/cloud default login is blocked in code, but Jacob must change this on the master PC before sharing any access.

---

### 4. Cloud production env vars not set locally (P2 — expected)

Required at deploy time (see `cloud_hosting/env.example`):

| Variable | Purpose |
|----------|---------|
| `JRC_PUBLIC_HOST_MODE=1` | HTTPS headers, block remote default admin |
| `JRC_SECRET_KEY` | Flask session secret |
| `JRC_TRUSTED_HOSTS` | Allowed hostnames |
| `JRC_DATA_DIR` | Persistent volume path |

---

### 5. `test_win11_ui_compat` fails in headless/CI (P2)

```
_tkinter.TclError: invalid command name "tcl_findLibrary"
```

Pre-existing environment issue — Tkinter needs a display on this audit machine. Does not affect Jacob's Windows desktop usage. Exclude with `--ignore=tests/test_win11_ui_compat.py` in CI until a headless skip is added.

---

## Tech Debt — Not Addressed on This Branch

| Item | Severity | Notes |
|------|----------|-------|
| Monolithic files (`network_server.py` ~5k lines, `jr_job_manager.py` ~2.5k) | Medium | Hard to maintain; split in future refactor |
| Unpinned `requirements.txt` | Medium | Reproducible builds may drift |
| No CSRF tokens on web forms | Medium | OK on private LAN; add for public cloud |
| HTTP on LAN host | Low | By design for local Wi-Fi |
| 100+ broad `except Exception:` blocks | Low | Errors may be swallowed silently |
| No login rate limiting | Medium | Account requests rate-limited; login endpoint is not |
| Owner PII hardcoded in source | Low | `enragementwow@hotmail.com` — should move to config |
| `mobile_quick_log` referenced in ai_viability_matrix but no tool file | Low | May cause future import errors if wired into registry |
| Disk data isolation audit not run in v8_build_verify pass | Low | May have env-specific failures |

---

## Recommended Next Steps for Jacob

### Before sharing with anyone
1. Merge this branch (or cherry-pick fixes)
2. Run install on master PC: `Launch-JRC-Manager.bat`
3. Change `admin / ivygrows` password immediately
4. Link `dropbox-records` workspace

### Before cloud go-live
5. Set cloud env vars per `cloud_hosting/env.example`
6. Deploy to Render/Railway with persistent disk
7. Run full QA from Start Center → Self Setup + Verify
8. Test mobile PWA + messenger from phone on same network

### Verify fixes landed
```powershell
cd J-and-R-construction-management
RUN_SYSTEM_TEST_SUITE.bat
# or:
.venv\Scripts\python.exe -m app.run_full_system_test_suite --standard
```
Full guide: `docs/SYSTEM_TEST_SUITE_GUIDE.md`

---

## Audit Scope

This audit covered:
- Full `main` branch clone (v8.1.0)
- 32 automated tests + 5 subtests
- 15+ QA/verification scripts
- Schema migration testing (desktop ↔ web shared DB)
- Office AI tool registry and import chain
- RBAC/security static and runtime audits
- v8 build manifest, route smoke, cloud deploy checks

**Verdict after this branch:** Core crash bugs fixed and tested. **Not fully production-ready** until Dropbox workspace is linked, default password changed, and cloud env is configured.
