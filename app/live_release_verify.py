# -*- coding: utf-8 -*-
"""Live release verification — Dropbox office DB alignment, pipelines, chat, standards."""
from __future__ import annotations

import csv
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

OFFICE_RATES = {
    "std_owner_hourly_rate": "30",
    "std_owner_daily_rate": "240",
    "std_helper_daily_rate": "140",
    "std_helper_overhead_per_work": "50",
}


def _count_register_jobs(dropbox: Path) -> int:
    reg = dropbox / "08_Admin_Standards" / "JRC_JOB_RELATION_REGISTER.csv"
    if not reg.is_file():
        return 0
    n = 0
    with reg.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = (row.get("Job_Code") or "").strip()
            if code and code not in ("JRC-ADM", "JRC-GEN"):
                n += 1
    return n


def sync_standards_files(base_dir: Path, dropbox: Path) -> List[str]:
    """Mirror key office standard docs into install business_standards/ (not business DB)."""
    notes: List[str] = []
    dest = base_dir / "business_standards"
    dest.mkdir(parents=True, exist_ok=True)
    copies = [
        (
            dropbox / "08_Admin_Standards" / "DOCUMENT_GENERATION_STANDARDS.txt",
            "DOCUMENT_GENERATION_STANDARDS.txt",
        ),
        (
            dropbox / "08_Admin_Standards" / "CUSTOMER_ONEDRIVE_SHARE_STANDARD.txt",
            "CUSTOMER_ONEDRIVE_SHARE_STANDARD.txt",
        ),
        (
            dropbox / "00_START_HERE" / "LOGGING_STANDARDS_OFFICE_ASSISTANT.txt",
            "LOGGING_STANDARDS_OFFICE_ASSISTANT.txt",
        ),
        (
            dropbox / "00_START_HERE" / "PHONE_CURSOR_DROPBOX_WORKSPACE.txt",
            "PHONE_CURSOR_DROPBOX_WORKSPACE.txt",
        ),
        (
            dropbox / "08_Admin_Standards" / "HELPER_WORK_OVERHEAD_RULE.txt",
            "HELPER_WORK_OVERHEAD_RULE.txt",
        ),
    ]
    for src, name in copies:
        if src.is_file():
            text = src.read_text(encoding="utf-8", errors="replace")
            (dest / name).write_text(text, encoding="utf-8")
            notes.append(f"standards file synced: {name}")
    manifest = {
        "synced_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dropbox_records": str(dropbox),
        "rates": OFFICE_RATES,
    }
    (dest / "OFFICE_STANDARDS_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    notes.append("OFFICE_STANDARDS_MANIFEST.json written")
    return notes


def verify_database_alignment(base_dir: Path) -> Tuple[List[str], List[str], Dict[str, Any]]:
    """Run office sync then validate DB vs Dropbox register."""
    from app.office_records_sync import find_dropbox_records, run_office_sync

    os.environ.setdefault(
        "JRC_DROPBOX_RECORDS",
        r"c:\Users\enrag\projects\JRC-Construction-Office\dropbox-records",
    )
    os.environ["JRC_DATA_DIR"] = str(base_dir / "data")
    os.environ["JRC_DB_PATH"] = str(base_dir / "data" / "jr_business.db")

    errors: List[str] = []
    notes: List[str] = []
    stats: Dict[str, Any] = {"base_dir": str(base_dir)}

    dropbox = find_dropbox_records(base_dir)
    if not dropbox:
        errors.append("dropbox-records not found")
        return notes, errors, stats

    stats["dropbox_records"] = str(dropbox)
    sync_standards_files(base_dir, dropbox)
    notes.append("business_standards/ synced from Dropbox office files")

    db_path = base_dir / "data" / "jr_business.db"
    if not db_path.is_file():
        errors.append(f"database missing: {db_path}")
        return notes, errors, stats

    try:
        from app.db_health import ensure_database_healthy

        ok, health_msg = ensure_database_healthy(db_path, log_dir=base_dir / "logs")
        notes.append(f"db health: {health_msg}")
        if not ok:
            errors.append(f"database unhealthy: {health_msg}")
            return notes, errors, stats
    except Exception as exc:
        errors.append(f"database health check failed: {exc}")
        return notes, errors, stats

    try:
        rep = run_office_sync(base_dir)
        stats["office_sync"] = rep
        for e in rep.get("errors") or []:
            errors.append(str(e))
        notes.extend(rep.get("notes") or [])
    except sqlite3.DatabaseError as exc:
        errors.append(f"office sync failed (database): {exc}")
        return notes, errors, stats
    except Exception as exc:
        errors.append(f"office sync failed: {exc}")

    if not db_path.is_file():
        errors.append(f"database missing after sync: {db_path}")
        return notes, errors, stats

    conn = sqlite3.connect(db_path, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        from app.db_health import configure_sqlite_connection

        configure_sqlite_connection(conn)
        qc = conn.execute("PRAGMA quick_check").fetchone()[0]
        if str(qc).lower() != "ok":
            errors.append(f"integrity quick_check: {qc}")
            return notes, errors, stats
        expected = _count_register_jobs(dropbox)
        db_codes = {
            r[0]
            for r in conn.execute(
                "SELECT job_code FROM jobs WHERE job_code IS NOT NULL AND job_code != ''"
            ).fetchall()
        }
        stats["register_job_count"] = expected
        stats["db_job_code_count"] = len(db_codes)
        if len(db_codes) < expected:
            errors.append(
                f"jobs in DB ({len(db_codes)}) fewer than office register ({expected})"
            )
        else:
            notes.append(f"job codes in DB: {len(db_codes)} (register expects {expected})")

        for key, val in OFFICE_RATES.items():
            row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
            if not row or str(row[0]) != val:
                errors.append(f"app_settings {key} expected {val}, got {row[0] if row else 'missing'}")
            else:
                notes.append(f"rate OK: {key}={val}")

        from app.live_chat import ensure_live_chat_schema

        ensure_live_chat_schema(conn)

        try:
            from app.schema_migrations import ensure_all_shared_schemas

            ensure_all_shared_schemas(conn)
        except Exception:
            pass

        for table in (
            "live_chat_sessions",
            "live_chat_messages",
        ):
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone():
                errors.append(f"missing table: {table}")

        for table in ("customer_job_requests", "permissions_override"):
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone():
                notes.append(f"optional table not yet created: {table} (created on first server start)")

        bc = conn.execute(
            "SELECT id FROM live_chat_sessions WHERE channel_type='admin_broadcast' LIMIT 1"
        ).fetchone()
        if not bc:
            errors.append("Office Announcements chat channel missing")
        else:
            notes.append("live chat admin_broadcast channel OK")

        stats["users"] = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        stats["customers"] = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        stats["jobs"] = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    finally:
        conn.close()

    return notes, errors, stats


def verify_install_paths() -> Tuple[List[str], List[str]]:
    """Verify all live install copies."""
    errors: List[str] = []
    notes: List[str] = []
    paths = [
        BASE_DIR,
        Path(os.environ.get("LOCALAPPDATA", "")) / "J_and_R_Construction_Manager",
    ]
    desktop = Path.home() / "OneDrive" / "Desktop" / "J and R Construction Manager"
    if not desktop.exists():
        desktop = Path.home() / "Desktop" / "J and R Construction Manager"
    if desktop.exists():
        paths.append(desktop)

    for p in paths:
        if not p.exists():
            continue
        label = p.name or str(p)
        notes.append(f"--- {label} ---")
        try:
            n, e, st = verify_database_alignment(p)
            notes.extend(n[:8])
            if e:
                errors.extend(f"{label}: {x}" for x in e)
            else:
                notes.append(f"{label}: DB aligned ({st.get('db_job_code_count', '?')} job codes)")
        except Exception as exc:
            errors.append(f"{label}: verify failed: {exc}")
    return notes, errors


def run_live_release_verify(base_dir: Path | None = None) -> Tuple[int, Path]:
    base = Path(base_dir or BASE_DIR).resolve()
    lines = [
        "J & R CONSTRUCTION MANAGER — LIVE RELEASE VERIFY",
        "=" * 62,
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    errors = 0

    lines.append("DROPBOX DATABASE ALIGNMENT (all installs)")
    notes, errs = verify_install_paths()
    lines.extend(f"  {n}" for n in notes)
    for e in errs:
        lines.append(f"  [ERROR] {e}")
        errors += 1
    lines.append("")

    lines.append("DATA PIPELINE")
    try:
        from app.data_pipeline import get_data_mode, verify_pipelines, write_pipeline_manifest

        write_pipeline_manifest()
        lines.append(f"  mode: {get_data_mode()}")
        for level, comp, detail in verify_pipelines():
            lines.append(f"  [{level}] {comp}: {detail}")
            if level == "ERROR":
                errors += 1
        lines.append("")
    except Exception as exc:
        lines.append(f"  pipeline error: {exc}")
        errors += 1

    lines.append("LIVE CHAT + UI CHECKS")
    ns = (base / "app" / "network_server.py").read_text(encoding="utf-8", errors="ignore")
    lc = (base / "app" / "live_chat.py").read_text(encoding="utf-8", errors="ignore")
    dc = (base / "app" / "dashboard_config.py").read_text(encoding="utf-8", errors="ignore")
    checks = [
        ("live_chat routes registered", "register_live_chat_routes" in ns),
        ("chat nav item", "Live Chat" in dc or "Live Chat" in ns),
        ("admin broadcast channel", "admin_broadcast" in lc),
        ("customer chat restricted", "is_customer_or_external" in lc),
        ("api chat sessions", "/api/chat/sessions" in lc),
        ("create team session", "create_team_session" in lc or "New team chat" in lc),
        ("global login gate", "enforce_global_login_required" in ns),
        ("unified dashboard config", "dashboard_config" in ns or "render_dashboard_sections" in ns),
        ("expanded hire roles", "helper" in ns and "subcontractor" in ns),
        ("account owner approval required", "approval_required" in ns and "notify_owner_new_account_request" in ns),
        ("requester email on approve/deny", "notify_requester_account_decision" in ns),
        ("file access security module", (base / "app" / "file_access_security.py").is_file()),
        ("indexed file role guard", "role_may_open_indexed_file" in ns),
        ("admin inline role change", "quick_change_user_role" in ns and "apply_user_role_change" in ns),
    ]
    for name, ok in checks:
        lines.append(f"  {'OK' if ok else 'ERROR'}: {name}")
        if not ok:
            errors += 1
    lines.append("")

    lines.append(f"SUMMARY: {errors} error(s)")
    lines.append("PASS" if errors == 0 else "NEEDS ATTENTION")

    report = base / "exports" / f"JRC_Live_Release_Verify_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8")
    (base / "LIVE_RELEASE_VERIFY_REPORT.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nReport: {report}")
    return errors, report


def main() -> int:
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE_DIR
    code, _ = run_live_release_verify(base)
    return 1 if code else 0


if __name__ == "__main__":
    raise SystemExit(main())
