# -*- coding: utf-8 -*-
"""Read-only consistency audit — app DB vs Dropbox office CSVs."""
from __future__ import annotations

import csv
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _db_path(base_dir: Path) -> Path:
    import os

    data = os.environ.get("JRC_DATA_DIR", str(base_dir / "data"))
    return Path(data) / "jr_business.db"


def run_read_only_audit(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    from app.dropbox_workspace import resolve_dropbox_records

    base = base_dir or Path(__file__).resolve().parents[2]
    report: Dict[str, Any] = {
        "ok": True,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "issues": [],
        "checks": [],
    }
    dropbox = resolve_dropbox_records(base)
    if not dropbox:
        report["issues"].append("dropbox-records not found")
        report["ok"] = False
        return report

    reg_path = dropbox / "08_Admin_Standards" / "JRC_JOB_RELATION_REGISTER.csv"
    if reg_path.is_file():
        with reg_path.open(encoding="utf-8", errors="ignore") as f:
            reg_rows = list(csv.DictReader(f))
        report["checks"].append({"name": "job_register", "count": len(reg_rows), "ok": True})
    else:
        report["issues"].append("Missing JRC_JOB_RELATION_REGISTER.csv")
        report["ok"] = False

    dbp = _db_path(base)
    if dbp.is_file():
        conn = sqlite3.connect(dbp)
        try:
            try:
                job_n = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
                report["checks"].append({"name": "db_jobs", "count": job_n, "ok": True})
            except sqlite3.Error as exc:
                report["issues"].append(f"jobs table: {exc}")
                report["ok"] = False
        finally:
            conn.close()
    else:
        report["issues"].append("Program database not found")

    for rel in (
        "04_FINANCIAL_TRACKING/Payroll_Helper_Register.csv",
        "04_FINANCIAL_TRACKING/Income_Deposit_Balance_Register.csv",
    ):
        p = dropbox / rel.replace("/", "\\")
        p = dropbox / Path(rel)
        if p.is_file():
            report["checks"].append({"name": rel, "ok": True})
        else:
            report["issues"].append(f"Missing {rel}")

    sync_markers = [
        dropbox / "08_Admin_Standards" / "FOLDER_SYNC_LAST_RUN.txt",
        dropbox / "08_Admin_Standards" / "WORKSPACE_SYNC_LAST_RUN.txt",
    ]
    for m in sync_markers:
        if m.is_file():
            age_h = (datetime.now().timestamp() - m.stat().st_mtime) / 3600
            stale = age_h > 48
            report["checks"].append({"name": m.name, "age_hours": round(age_h, 1), "stale": stale})
            if stale:
                report["issues"].append(f"{m.name} older than 48h")

    dash = dropbox / "00_START_HERE" / "READABLE" / "BUSINESS_DASHBOARD.txt"
    if dash.is_file():
        text = dash.read_text(encoding="utf-8", errors="ignore")
        if len(text.strip()) < 200 or "TEMPLATE_STUB" in text.upper():
            report["issues"].append("BUSINESS_DASHBOARD.txt looks like stub or empty")
    else:
        report["issues"].append("Missing BUSINESS_DASHBOARD.txt readable copy")

    if report["issues"]:
        report["ok"] = False
    return report


def format_report(report: Dict[str, Any]) -> str:
    lines = [
        "J & R Construction — Consistency Audit (read-only)",
        f"Timestamp: {report.get('timestamp')}",
        f"Status: {'PASS' if report.get('ok') else 'ISSUES FOUND'}",
        "",
    ]
    for issue in report.get("issues") or []:
        lines.append(f"  ISSUE: {issue}")
    lines.append("")
    lines.append("Checks:")
    for chk in report.get("checks") or []:
        lines.append(f"  - {chk}")
    return "\n".join(lines)
