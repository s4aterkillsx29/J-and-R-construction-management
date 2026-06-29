# -*- coding: utf-8 -*-
"""Full workspace log/sync — phone Dropbox edits → PC refresh → standards both ways."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("JRC_DATA_DIR", str(BASE_DIR / "data"))).expanduser()
DB_PATH = Path(os.environ.get("JRC_DB_PATH", str(DATA_DIR / "jr_business.db"))).expanduser()
EXPORT_DIR = Path(os.environ.get("JRC_EXPORT_DIR", str(BASE_DIR / "exports"))).expanduser()
STANDARDS_DIR = BASE_DIR / "business_standards"
APP_VERSION = "7.13.0"

# Workspace → install (Dropbox is source of truth for office docs)
WORKSPACE_TO_INSTALL = [
    ("08_Admin_Standards/DOCUMENT_GENERATION_STANDARDS.txt", "DOCUMENT_GENERATION_STANDARDS.txt"),
    ("08_Admin_Standards/CUSTOMER_ONEDRIVE_SHARE_STANDARD.txt", "CUSTOMER_ONEDRIVE_SHARE_STANDARD.txt"),
    ("08_Admin_Standards/HELPER_WORK_OVERHEAD_RULE.txt", "HELPER_WORK_OVERHEAD_RULE.txt"),
    ("00_START_HERE/LOGGING_STANDARDS_OFFICE_ASSISTANT.txt", "LOGGING_STANDARDS_OFFICE_ASSISTANT.txt"),
    ("00_START_HERE/PHONE_CURSOR_DROPBOX_WORKSPACE.txt", "PHONE_CURSOR_DROPBOX_WORKSPACE.txt"),
]

# Install → workspace (push app-exported standards back to Dropbox for phone)
INSTALL_TO_WORKSPACE = [
    ("JRC_Business_Document_Standards.json", "08_Admin_Standards/JRC_Business_Document_Standards.json"),
    ("JRC_Business_Document_Standards.csv", "08_Admin_Standards/JRC_Business_Document_Standards.csv"),
    ("OFFICE_STANDARDS_MANIFEST.json", "08_Admin_Standards/OFFICE_STANDARDS_MANIFEST.json"),
]


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sync_standards_workspace_to_install(workspace: Path, base_dir: Path) -> List[str]:
    """Pull latest office standards from Dropbox workspace into install folder."""
    notes: List[str] = []
    dest = base_dir / "business_standards"
    dest.mkdir(parents=True, exist_ok=True)
    for rel, name in WORKSPACE_TO_INSTALL:
        src = workspace / rel.replace("/", os.sep)
        if src.is_file():
            text = src.read_text(encoding="utf-8", errors="replace")
            (dest / name).write_text(text, encoding="utf-8")
            notes.append(f"pulled standard: {name}")
    manifest = {
        "synced_at": _stamp(),
        "workspace_root": str(workspace),
        "direction": "workspace_to_install",
        "app_version": APP_VERSION,
    }
    (dest / "OFFICE_STANDARDS_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    notes.append("OFFICE_STANDARDS_MANIFEST.json updated (workspace → install)")
    return notes


def sync_standards_install_to_workspace(workspace: Path, base_dir: Path) -> List[str]:
    """Push install standards exports to Dropbox so phone sees latest."""
    notes: List[str] = []
    src_dir = base_dir / "business_standards"
    if not src_dir.is_dir():
        return notes
    for name, rel in INSTALL_TO_WORKSPACE:
        src = src_dir / name
        if not src.is_file():
            continue
        dest = workspace / rel.replace("/", os.sep)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        notes.append(f"pushed standard: {rel}")
    rates_note = workspace / "08_Admin_Standards" / "JRC_MANAGER_RATES_LAST_SYNC.txt"
    rates_note.parent.mkdir(parents=True, exist_ok=True)
    rates_note.write_text(
        f"Rates/standards pushed from Construction Manager at {_stamp()}\n"
        f"App version: {APP_VERSION}\n",
        encoding="utf-8",
    )
    notes.append("JRC_MANAGER_RATES_LAST_SYNC.txt written")
    return notes


def mirror_bookkeeping_readable(workspace: Path, base_dir: Path) -> List[str]:
    """Copy key CSV mirrors into 06_Bookkeeping_Taxes for readable phone access."""
    notes: List[str] = []
    dest_root = workspace / "06_Bookkeeping_Taxes"
    dest_root.mkdir(parents=True, exist_ok=True)
    sources = [
        (workspace / "04_FINANCIAL_TRACKING" / "Income_Deposits_Balances" / "Income_Deposit_Balance_Register.csv", "Income_Deposit_Balance_Register.csv"),
        (workspace / "05_Helper_Pay_Workers" / "Payroll_Helper_Register.csv", "Payroll_Helper_Register.csv"),
        (base_dir / "exports" / "office_sync" / "Payroll_Helper_Export_Preview.csv", "Payroll_Helper_Export_Preview.csv"),
        (base_dir / "exports" / "office_sync" / "Income_Deposit_Export_Preview.csv", "Income_Deposit_Export_Preview.csv"),
    ]
    for src, name in sources:
        if src.is_file():
            shutil.copy2(src, dest_root / name)
            notes.append(f"mirrored bookkeeping: {name}")
    return notes


def write_business_dashboard(workspace: Path, report: Dict[str, Any]) -> Path:
    """Rebuild READABLE dashboard with last sync timestamp for phone/PC alignment check."""
    readable = workspace / "00_START_HERE" / "READABLE"
    readable.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    lines = [
        "J & R CONSTRUCTION — BUSINESS DASHBOARD (READABLE)",
        f"Last PC sync: {stamp}",
        f"App version: {APP_VERSION}",
        f"Workspace: {workspace}",
        "",
        "ALIGNMENT CHECK: same date/time on Last PC sync (phone vs PC) = you are aligned.",
        "",
    ]
    reg = workspace / "08_Admin_Standards" / "JRC_JOB_RELATION_REGISTER.csv"
    if reg.is_file():
        lines.extend(["ACTIVE JOBS", "-----------"])
        import csv

        with reg.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                code = (row.get("Job_Code") or "").strip()
                if code and code not in ("JRC-ADM", "JRC-GEN"):
                    lines.append(
                        f"  {code} — {row.get('Customer', '')} — {row.get('Address', '')} — {row.get('Status', '')}"
                    )
        lines.append("")

    lines.extend(
        [
            "PHONE VERIFY: 00_START_HERE/JRC-315_LILY_FENCE_QUOTE_CURRENT.txt → $13,890",
            "",
            "DAILY HABIT:",
            "  Field (phone): log work in this Dropbox workspace.",
            "  Evening (PC): tell desktop Cursor 'log' or run Sync Business Workspace.",
            "  Check: this file on both devices — same Last PC sync = aligned.",
            "",
            "LAST SYNC SUMMARY:",
        ]
    )
    for n in report.get("notes") or []:
        lines.append(f"  - {n}")
    for e in report.get("errors") or []:
        lines.append(f"  ! {e}")

    out = readable / "BUSINESS_DASHBOARD.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def append_sync_log(workspace: Path, report: Dict[str, Any]) -> Path:
    """Append timestamped sync entry — audit trail for phone + PC."""
    readable = workspace / "00_START_HERE" / "READABLE"
    readable.mkdir(parents=True, exist_ok=True)
    log_path = readable / "SYNC_LOG.txt"
    entry = [
        f"[{_stamp()}] workspace sync",
        f"  ok={report.get('ok')} workspace={report.get('workspace')}",
        f"  app={APP_VERSION}",
    ]
    for n in (report.get("notes") or [])[:12]:
        entry.append(f"  + {n}")
    for e in report.get("errors") or []:
        entry.append(f"  ! {e}")
    entry.append("")
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(entry))
    last = readable / "LAST_SYNC.json"
    last.write_text(
        json.dumps(
            {
                "synced_at": _stamp(),
                "ok": report.get("ok"),
                "workspace": report.get("workspace"),
                "app_version": APP_VERSION,
                "notes_count": len(report.get("notes") or []),
                "errors": report.get("errors") or [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return log_path


def run_full_workspace_sync(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Master log/sync — run on PC after phone field work (or anytime to align)."""
    base = base_dir or BASE_DIR
    report: Dict[str, Any] = {
        "ok": False,
        "workspace": None,
        "base_dir": str(base),
        "synced_at": _stamp(),
        "app_version": APP_VERSION,
        "notes": [],
        "errors": [],
    }

    from app.jrc_workspace import ensure_unified_workspace, workspace_layout, write_workspace_manifest
    from app.phone_cursor_workspace import deploy_templates, verify_phone_workspace

    unified = ensure_unified_workspace(base)
    if not unified.get("ok"):
        report["errors"].extend(unified.get("errors") or ["workspace not found"])
        return report

    workspace = Path(unified["workspace"])
    report["workspace"] = str(workspace)
    report["notes"].extend(unified.get("notes") or [])

    try:
        report["notes"].extend(deploy_templates(workspace))
        write_workspace_manifest(workspace)
    except Exception as exc:
        report["errors"].append(f"deploy templates: {exc}")

    try:
        report["notes"].extend(sync_standards_workspace_to_install(workspace, base))
        report["notes"].extend(sync_standards_install_to_workspace(workspace, base))
    except Exception as exc:
        report["errors"].append(f"standards sync: {exc}")

    try:
        from app.office_records_sync import run_office_sync

        os.environ["JRC_DATA_DIR"] = str(base / "data")
        os.environ["JRC_DB_PATH"] = str(base / "data" / "jr_business.db")
        office_rep = run_office_sync(base)
        report["office_sync"] = office_rep
        report["notes"].extend(office_rep.get("notes") or [])
        for e in office_rep.get("errors") or []:
            report["errors"].append(str(e))
    except Exception as exc:
        report["errors"].append(f"office sync: {exc}")

    try:
        if DB_PATH.is_file():
            conn = sqlite3.connect(DB_PATH)
            try:
                from app.dropbox_business import ensure_dropbox_file_source, get_dropbox_folder, set_setting

                set_setting(conn, "jrc_workspace_root", str(workspace))
                set_setting(conn, "dropbox_folder", str(workspace))
                folder = ensure_dropbox_file_source(conn)
                if folder:
                    report["notes"].append(f"file source registered: {folder}")
            finally:
                conn.close()
    except Exception as exc:
        report["errors"].append(f"dropbox file source: {exc}")

    try:
        report["notes"].extend(mirror_bookkeeping_readable(workspace, base))
    except Exception as exc:
        report["errors"].append(f"bookkeeping mirror: {exc}")

    try:
        dash = write_business_dashboard(workspace, report)
        report["notes"].append(f"dashboard: {dash.name}")
        log_path = append_sync_log(workspace, report)
        report["notes"].append(f"sync log: {log_path.name}")
    except Exception as exc:
        report["errors"].append(f"dashboard/log: {exc}")

    try:
        verify = verify_phone_workspace(workspace)
        if not verify.get("ok"):
            report["errors"].extend(verify.get("errors") or ["phone verify failed"])
        else:
            report["notes"].append("phone workspace verify OK ($13,890 quote)")
    except Exception as exc:
        report["errors"].append(f"verify: {exc}")

    report["ok"] = not report["errors"]
    export_report(base, report)
    return report


def export_report(base_dir: Path, report: Dict[str, Any]) -> Path:
    export_dir = base_dir / "exports" / "workspace_sync"
    export_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    json_path = export_dir / f"WORKSPACE_SYNC_{stamp}.json"
    txt_path = export_dir / "WORKSPACE_SYNC_LAST.txt"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "J & R Construction — Workspace Sync Report",
        f"Time: {report.get('synced_at')}",
        f"OK: {report.get('ok')}",
        f"Workspace: {report.get('workspace')}",
        "",
        "Notes:",
    ]
    lines.extend(f"  - {n}" for n in report.get("notes") or [])
    if report.get("errors"):
        lines.extend(["", "Errors:"])
        lines.extend(f"  ! {e}" for e in report["errors"])
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return txt_path


def format_report(report: Dict[str, Any]) -> str:
    lines = [
        "J & R Construction — Full Workspace Sync (log)",
        f"OK: {report.get('ok')}",
        f"Time: {report.get('synced_at')}",
        f"Workspace: {report.get('workspace')}",
        "",
    ]
    for n in report.get("notes") or []:
        lines.append(f"  + {n}")
    for e in report.get("errors") or []:
        lines.append(f"  ! {e}")
    if report.get("ok"):
        lines.extend(
            [
                "",
                "Phone + PC aligned when BUSINESS_DASHBOARD.txt shows the same Last PC sync on both.",
                "Check: 00_START_HERE/READABLE/BUSINESS_DASHBOARD.txt",
            ]
        )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    import sys

    args = list(argv if argv is not None else sys.argv[1:])
    base = Path(args[0]) if args and not args[0].startswith("-") else BASE_DIR
    rep = run_full_workspace_sync(base)
    print(format_report(rep))
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
