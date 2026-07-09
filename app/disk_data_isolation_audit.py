# -*- coding: utf-8 -*-
"""Triple-check: business data on disk only where allowed; role isolation enforced."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

OWNER_INSTALL_MARKERS = (
    "J and R Construction Manager",
    "J-and-R-construction-management",
)
WORKER_PROFILE = "WorkerClient"
SENSITIVE_DIR_NAMES = (
    "04_financial_tracking",
    "06_bookkeeping_taxes",
    "payroll",
    "tax_2026",
)


def _home() -> Path:
    return Path.home()


def _candidate_installs() -> list[Path]:
    paths = [
        _home() / "OneDrive" / "Desktop" / "J and R Construction Manager",
        _home() / "Desktop" / "J and R Construction Manager",
        Path(os.environ.get("LOCALAPPDATA", "")) / "J_and_R_Construction_Manager",
        _home() / "Documents" / "JRC" / "J-and-R-construction-management",
        BASE,
    ]
    out: list[Path] = []
    seen: set[str] = set()
    for p in paths:
        key = str(p).lower()
        if key not in seen and p.exists():
            seen.add(key)
            out.append(p)
    return out


def _read_profile(install: Path) -> dict:
    for rel in ("data/install_profile.json", "data\\install_profile.json"):
        fp = install / rel
        if fp.exists():
            try:
                return json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                return {}
    return {}


def _db_user_summary(db_path: Path) -> dict:
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        active = conn.execute("SELECT username, role FROM users WHERE active=1").fetchall()
        admins = conn.execute("SELECT username, active FROM users WHERE role='admin'").fetchall()
        conn.close()
        return {
            "active": [dict(r) for r in active],
            "admins": [(r["username"], r["active"]) for r in admins],
        }
    except Exception as exc:
        return {"error": str(exc)}


def run_disk_data_isolation_audit(base_dir: Path | None = None) -> tuple[int, Path]:
    base = Path(base_dir or BASE).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    ok: list[str] = []

    # Static security modules
    try:
        from app.file_access_security import verify_file_access_security

        if verify_file_access_security(base) != 0:
            errors.append("file_access_security static checks failed")
        else:
            ok.append("file_access_security static checks PASS")
    except Exception as exc:
        errors.append(f"file_access_security: {exc}")

    try:
        from app.role_permissions import PERMISSIONS

        customer = PERMISSIONS.get("customer", set())
        if "view_files" in customer or "view_money" in customer or "view_bookkeeping" in customer:
            errors.append("customer role has internal business permissions")
        else:
            ok.append("customer role has no internal file/money/bookkeeping perms")
        worker = PERMISSIONS.get("worker", set())
        if "view_bookkeeping" in worker or "view_money" in worker:
            errors.append("worker role has bookkeeping/money permissions")
        else:
            ok.append("worker role blocked from bookkeeping/money perms")
    except Exception as exc:
        errors.append(f"role_permissions: {exc}")

    ns = (base / "app" / "network_server.py").read_text(encoding="utf-8", errors="ignore")
    if "filter_indexed_files_for_role" in ns and "role_may_see_file_source_paths" in ns:
        ok.append("file listing filtered by role in /files and mobile API")
    else:
        errors.append("file listing role filter missing from network_server")

    # Disk scan — installs and databases
    installs = _candidate_installs()
    ok.append(f"Scanned {len(installs)} install location(s)")

    public_desktop = _home() / "Public" / "Desktop"
    for db in public_desktop.rglob("jr_business.db") if public_desktop.exists() else []:
        errors.append(f"Business DB on Public Desktop (remove): {db}")

    owner_db_count = 0
    worker_with_db: list[str] = []

    for install in installs:
        profile = _read_profile(install)
        prof_name = profile.get("profile", "unknown")
        allow_local = profile.get("allow_local_business_data", True)
        db_path = install / "data" / "jr_business.db"
        is_owner_marker = any(m.lower() in str(install).lower() for m in OWNER_INSTALL_MARKERS)

        if db_path.exists():
            owner_db_count += 1
            summary = _db_user_summary(db_path)
            if summary.get("error"):
                warnings.append(f"{install.name}: DB read warning — {summary['error']}")
            else:
                active = summary.get("active", [])
                if len(active) == 1 and active[0].get("username") == "admin":
                    ok.append(f"{install.name}: single active admin only")
                elif active:
                    warnings.append(f"{install.name}: active users {[a['username'] for a in active]}")
                admins_active = [u for u, a in summary.get("admins", []) if a]
                if len(admins_active) > 1:
                    errors.append(f"{install.name}: multiple active admin accounts {admins_active}")

            if prof_name == WORKER_PROFILE or allow_local is False:
                worker_with_db.append(str(db_path))
        elif prof_name == WORKER_PROFILE:
            ok.append(f"{install.name}: WorkerClient — no local business DB (correct)")

        # Sensitive folders should only exist on owner/master installs
        if db_path.exists() and is_owner_marker:
            ok.append(f"{install.name}: owner install may store business data locally")

    if worker_with_db:
        for p in worker_with_db:
            errors.append(f"WorkerClient install has business DB on disk (remove or re-profile): {p}")

    if owner_db_count == 0:
        warnings.append("No jr_business.db found on scanned owner paths — host may be stopped")

    # Dropbox office junction (project)
    dropbox_records = base.parent / "dropbox-records"
    if not dropbox_records.exists():
        dropbox_records = Path(os.environ.get("JRC_DROPBOX_RECORDS", ""))
    if dropbox_records.exists():
        ok.append("dropbox-records office folder present (owner PC only — do not copy to worker clients)")
    else:
        warnings.append("dropbox-records junction not found from repo (may be OK on worker client)")

    lines = [
        "JRC DISK DATA ISOLATION AUDIT",
        time.strftime("%Y-%m-%d %H:%M:%S"),
        f"Base: {base}",
        "",
        f"SUMMARY: {len(errors)} error(s), {len(warnings)} warning(s), {len(ok)} OK",
        "",
        "ERRORS:",
    ]
    lines += [f"  - {e}" for e in errors] or ["  - None"]
    lines += ["", "WARNINGS:"]
    lines += [f"  - {w}" for w in warnings] or ["  - None"]
    lines += ["", "OK:"]
    lines += [f"  - {x}" for x in ok[:35]]
    if len(ok) > 35:
        lines.append(f"  ... and {len(ok) - 35} more")

    out = base / "exports" / f"JRC_Disk_Data_Isolation_Audit_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nReport: {out}")
    return len(errors), out


def main() -> int:
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE
    code, _ = run_disk_data_isolation_audit(base)
    return 1 if code else 0


if __name__ == "__main__":
    raise SystemExit(main())
