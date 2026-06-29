#!/usr/bin/env python3
"""Upload Lily stair invoices across Dropbox folders, sync standards, and update log."""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"
DB_PATH = DATA_DIR / "jr_business.db"
SEND_DIR = BASE_DIR / "docs" / "quotes" / "lily-315-sassafras" / "SEND_TO_LILY"
STANDARDS_DIR = BASE_DIR / "business_standards"
TEMPLATES_DIR = BASE_DIR / "document_templates"
DEFAULT_DROPBOX_ROOT = BASE_DIR / "dropbox_business"
LOG_MIRROR_FILENAME = "JRC_Business_Log_Latest.txt"

DROPBOX_ORGANIZATION_FOLDERS = [
    "00_INBOX_To_File",
    "01_Jobs/Active",
    "01_Jobs/Completed",
    "01_Jobs/Leads_Estimates",
    "02_Documents_Invoices_Estimates_Quotes",
    "03_Receipts_Materials/Needs_Review",
    "03_Receipts_Materials/Filed",
    "04_Photos_Evidence/Before",
    "04_Photos_Evidence/During",
    "04_Photos_Evidence/After",
    "05_Helper_Pay_Workers",
    "06_Bookkeeping_Taxes/Income",
    "06_Bookkeeping_Taxes/Expenses",
    "06_Bookkeeping_Taxes/Schedule_C",
    "07_Backups",
    "08_Admin_Standards",
    "09_Archive",
    "10_Logs",
    "11_Exports",
    "12_Imports_ChatGPT",
]

STAIR_INVOICES = [
    {
        "send_name": "Lily_315_Sassafras_Stair_Set_1_CUSTOMER_INVOICE.pdf",
        "legacy_name": "CUSTOMER_COPY_INV-JRC-JOB-315-LILY-STAIR-SET-01-001.pdf",
        "doc_no": "INV-JRC-JOB-315-LILY-STAIR-SET-01-001",
    },
    {
        "send_name": "Lily_315_Sassafras_Stair_Set_2_CUSTOMER_INVOICE.pdf",
        "legacy_name": "CUSTOMER_COPY_INV-JRC-JOB-315-LILY-STAIR-SET-02-001.pdf",
        "doc_no": "INV-JRC-JOB-315-LILY-STAIR-SET-02-001",
    },
]

STANDARDS_FILES = [
    STANDARDS_DIR / "JRC_Business_Document_Standards.json",
    STANDARDS_DIR / "JRC_Business_Document_Standards.csv",
    STANDARDS_DIR / "JRC_Log_Workflow_Standard.txt",
    STANDARDS_DIR / "JRC_Dropbox_Organization_Standard.txt",
    TEMPLATES_DIR / "JRC_Customer_Invoice_Template.txt",
]


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %I:%M %p")


def ensure_dropbox_organization(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel in DROPBOX_ORGANIZATION_FOLDERS:
        (root / rel).mkdir(parents=True, exist_ok=True)
    readme = root / "_JRC_DROPBOX_ORGANIZATION_README.txt"
    if not readme.exists():
        readme.write_text(
            "J & R Construction Dropbox organization\n\n"
            "Single Dropbox business root for jobs, documents, logs, standards, and exports.\n",
            encoding="utf-8",
        )
    return root


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def resolve_dropbox_root(conn: sqlite3.Connection) -> Path:
    configured = get_setting(conn, "dropbox_folder", "").strip()
    if configured:
        return ensure_dropbox_organization(Path(configured).expanduser())
    env_root = os.environ.get("JRC_DROPBOX_FOLDER", "").strip()
    if env_root:
        root = ensure_dropbox_organization(Path(env_root).expanduser())
        set_setting(conn, "dropbox_folder", str(root))
        return root
    root = ensure_dropbox_organization(DEFAULT_DROPBOX_ROOT)
    set_setting(conn, "dropbox_folder", str(root.resolve()))
    return root


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS business_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            category TEXT,
            entry TEXT
        );
        """
    )
    conn.commit()


def source_invoice(send_name: str) -> Path:
    path = SEND_DIR / send_name
    if path.exists():
        return path
    raise FileNotFoundError(f"Missing stair invoice source: {path}")


def copy_invoice(source: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return dest


def distribute_stair_invoices(dropbox_root: Path) -> list[Path]:
    """Copy both stair invoices to the Dropbox All Files folder (business root)."""
    saved: list[Path] = []
    all_files_dir = dropbox_root / "All Files"
    all_files_dir.mkdir(parents=True, exist_ok=True)

    for invoice in STAIR_INVOICES:
        source = source_invoice(invoice["send_name"])
        saved.append(copy_invoice(source, all_files_dir / invoice["send_name"]))
        saved.append(copy_invoice(source, dropbox_root / invoice["send_name"]))
        saved.append(copy_invoice(source, EXPORT_DIR / invoice["send_name"]))
    return saved


def sync_business_standards(dropbox_root: Path) -> list[Path]:
    saved: list[Path] = []
    STANDARDS_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    admin_dir = dropbox_root / "08_Admin_Standards"
    admin_dir.mkdir(parents=True, exist_ok=True)

    for src in STANDARDS_FILES:
        if not src.exists():
            continue
        saved.append(copy_invoice(src, admin_dir / src.name))
        export_copy = EXPORT_DIR / src.name
        if src.resolve() != export_copy.resolve():
            saved.append(copy_invoice(src, export_copy))
    return saved


def new_standards_summary() -> str:
    json_path = STANDARDS_DIR / "JRC_Business_Document_Standards.json"
    if not json_path.exists():
        return "No standards JSON found."
    data = json.loads(json_path.read_text(encoding="utf-8"))
    keys = [
        "preexisting_file_search_rule",
        "job_identity_lookup_rule",
        "job_document_number_rule",
        "document_delivery_link_rule",
        "log_command_rule",
        "dropbox_log_sync_rule",
        "dropbox_source_folder_standard",
        "dropbox_organization_repair_rule",
    ]
    found = [key for key in keys if key in data]
    return f"Saved {len(found)} newer Dropbox/document/log standards to business_standards and Dropbox 08_Admin_Standards."


def log_entry(conn: sqlite3.Connection, category: str, entry: str) -> None:
    conn.execute(
        "INSERT INTO business_log(timestamp, category, entry) VALUES(?,?,?)",
        (now_stamp(), category, entry),
    )
    conn.commit()


def mirror_business_log(conn: sqlite3.Connection, dropbox_root: Path) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        "SELECT timestamp, category, entry FROM business_log ORDER BY id DESC LIMIT 250"
    ).fetchall()
    lines = [
        "J and R Construction Manager business log mirror",
        f"Updated: {now_stamp()}",
        "",
    ]
    for timestamp, category, entry in reversed(rows):
        lines.append(f"[{timestamp}] {category}: {entry}")
    mirror_path = EXPORT_DIR / LOG_MIRROR_FILENAME
    mirror_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for rel in ("10_Logs", ""):
        target_dir = dropbox_root / rel if rel else dropbox_root
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mirror_path, target_dir / LOG_MIRROR_FILENAME)
    return mirror_path


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_schema(conn)
        dropbox_root = resolve_dropbox_root(conn)
        invoice_paths = distribute_stair_invoices(dropbox_root)
        standards_paths = sync_business_standards(dropbox_root)

        log_entry(
            conn,
            "Document",
            "Copied Lily / 315 Sassafras stair customer invoices to Dropbox All Files folder: "
            "Lily_315_Sassafras_Stair_Set_1_CUSTOMER_INVOICE.pdf and "
            "Lily_315_Sassafras_Stair_Set_2_CUSTOMER_INVOICE.pdf at $1,000.00 each.",
        )
        log_entry(conn, "Business Standards", new_standards_summary())
        log_entry(
            conn,
            "Dropbox",
            f"Synced business standards to Dropbox 08_Admin_Standards and refreshed log mirror at {dropbox_root}.",
        )
        mirror = mirror_business_log(conn, dropbox_root)

        print(f"Dropbox root: {dropbox_root}")
        print(f"Business log: {mirror}")
        print("\nStair invoice Dropbox copies:")
        for path in sorted({str(p) for p in invoice_paths if "dropbox_business" in str(p) or str(dropbox_root) in str(p)}):
            print(f"  {path}")
        print("\nStandards saved:")
        for path in sorted({p.name for p in standards_paths}):
            print(f"  {path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
