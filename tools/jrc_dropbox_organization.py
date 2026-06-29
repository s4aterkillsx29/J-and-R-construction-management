#!/usr/bin/env python3
"""J&R Construction Dropbox organization helpers.

Safe full reorganization:
1. Inventory everything first
2. Snapshot to 09_Archive before changes
3. Copy/move files into standard folders (never delete)
4. Write root navigation files
"""

from __future__ import annotations

import datetime as dt
import filecmp
import hashlib
import json
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"
DB_PATH = DATA_DIR / "jr_business.db"
DEFAULT_DROPBOX_ROOT = BASE_DIR / "dropbox_business"
LOG_MIRROR_FILENAME = "JRC_Business_Log_Latest.txt"

DROPBOX_LEGACY_SOURCE_CANDIDATES = [
    "Invoices2026 1.0",
    "J and R Construction",
    "JRC",
]

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

NON_STANDARD_ROOT_FOLDERS = {
    "All Files",
    "all files",
    "Invoices",
    "Documents",
    "Exports",
    "iphone_files",
}

ROOT_KEEP_FILES = {
    "START_HERE_NAVIGATION.txt",
    "_JRC_DROPBOX_ORGANIZATION_README.txt",
    "JRC_ROOT_INDEX.json",
}

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}
DOC_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".html", ".htm", ".csv", ".json"}
ARCHIVE_EXTENSIONS = {".zip", ".7z", ".bak"}


@dataclass
class ReorgReport:
    root: Path
    stamp: str
    inventory_count: int = 0
    snapshot_dir: Path | None = None
    copied: list[str] = field(default_factory=list)
    skipped_duplicate: list[str] = field(default_factory=list)
    archived_legacy: list[str] = field(default_factory=list)
    inbox_unsorted: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %I:%M %p")


def iso_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_dropbox_organization(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel in DROPBOX_ORGANIZATION_FOLDERS:
        (root / rel).mkdir(parents=True, exist_ok=True)
    return root


def discover_legacy_roots() -> list[Path]:
    roots: list[Path] = []
    home = Path.home()
    parents = [home / "Dropbox", home / "OneDrive" / "Desktop", home / "Documents", BASE_DIR]
    for parent in parents:
        if not parent.exists():
            continue
        for name in DROPBOX_LEGACY_SOURCE_CANDIDATES:
            candidate = parent / name
            if candidate.exists() and candidate.is_dir():
                roots.append(candidate)
    return roots


def resolve_dropbox_root(conn: sqlite3.Connection | None = None) -> Path:
    configured = ""
    if conn is not None:
        row = conn.execute("SELECT value FROM app_settings WHERE key='dropbox_folder'").fetchone()
        configured = (row[0] if row else "") or ""
    env_root = os.environ.get("JRC_DROPBOX_FOLDER", "").strip()
    if configured.strip():
        return Path(configured).expanduser()
    if env_root:
        return Path(env_root).expanduser()
    return DEFAULT_DROPBOX_ROOT


def set_dropbox_root(conn: sqlite3.Connection, root: Path) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.execute(
        "INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        ("dropbox_folder", str(root.resolve())),
    )
    conn.commit()


def inventory_tree(root: Path) -> list[dict]:
    rows: list[dict] = []
    if not root.exists():
        return rows
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        rows.append(
            {
                "relative_path": rel,
                "size": path.stat().st_size,
                "modified": dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                "sha256": file_hash(path),
            }
        )
    return rows


def classify_relative_destination(rel_path: str, filename: str) -> str:
    name = filename.lower()
    path_lower = rel_path.lower()

    if "internal" in name and ("cost" in name or "job_cost" in name):
        return "08_Admin_Standards/_Internal_Job_Costing"
    if any(k in name or k in path_lower for k in ("lily", "315", "sassafras")):
        return "02_Documents_Invoices_Estimates_Quotes/Lily_315_Sassafras"
    if any(k in name for k in ("receipt", "lowes", "home depot", "materials")):
        return "03_Receipts_Materials/Needs_Review"
    if name.endswith(tuple(PHOTO_EXTENSIONS)) or "/photo" in path_lower:
        if "after" in path_lower:
            return "04_Photos_Evidence/After"
        if "during" in path_lower:
            return "04_Photos_Evidence/During"
        return "04_Photos_Evidence/Before"
    if any(k in name for k in ("backup",)) or name.endswith(tuple(ARCHIVE_EXTENSIONS)):
        return "07_Backups"
    if any(k in name for k in ("standard", "template", "workflow")):
        return "08_Admin_Standards"
    if "business_log" in name or name.startswith("jrc_") and "log" in name:
        return "10_Logs"
    if any(k in name for k in ("export", "final_check", "verification")):
        return "11_Exports"
    if "chatgpt" in path_lower or "import" in path_lower:
        return "12_Imports_ChatGPT"
    if any(
        k in name
        for k in (
            "inv-",
            "est-",
            "invoice",
            "estimate",
            "quote",
            "customer",
            "proposal",
        )
    ):
        return "02_Documents_Invoices_Estimates_Quotes"
    if name.endswith(tuple(DOC_EXTENSIONS)):
        return "00_INBOX_To_File"
    return "00_INBOX_To_File"


def is_within_standard_tree(rel_path: str) -> bool:
    top = rel_path.split("/", 1)[0]
    # standard folders are numbered 00_..12_
    return bool(re.match(r"^\d{2}_", top))


def safe_copy_unique(source: Path, dest: Path, report: ReorgReport) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        try:
            if filecmp.cmp(source, dest, shallow=False):
                report.skipped_duplicate.append(f"{source} -> {dest} (identical)")
                return
        except Exception:
            pass
        stem, suffix = dest.stem, dest.suffix
        counter = 2
        while dest.exists():
            dest = dest.with_name(f"{stem}__copy{counter}{suffix}")
            counter += 1
    shutil.copy2(source, dest)
    report.copied.append(f"{source} -> {dest}")


def snapshot_root(root: Path, stamp: str) -> Path:
    snapshot = root / "09_Archive" / f"_PreReorg_Snapshot_{stamp}"
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in root.iterdir():
        if path.name in {"09_Archive"}:
            continue
        dest = snapshot / path.name
        if path.is_dir():
            shutil.copytree(path, dest, dirs_exist_ok=True)
        elif path.is_file():
            shutil.copy2(path, dest)
    return snapshot


def collect_files_to_organize(root: Path, extra_roots: list[Path]) -> list[tuple[Path, Path]]:
    """Return (source_path, path_relative_to_root) for files needing placement."""
    items: list[tuple[Path, Path]] = []

    def add_from(base: Path, prefix: Path | None = None) -> None:
        if not base.exists():
            return
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(base)
            if prefix:
                rel = prefix / rel
            rel_posix = rel.as_posix()
            if rel_posix.startswith("09_Archive/_PreReorg_Snapshot_"):
                continue
            if path.name in ROOT_KEEP_FILES:
                continue
            if is_within_standard_tree(rel_posix):
                top = rel_posix.split("/", 1)[0]
                if top in {f.split("/")[0] for f in DROPBOX_ORGANIZATION_FOLDERS}:
                    # already under a standard numbered folder
                    if rel_posix.count("/") >= 1:
                        continue
            items.append((path, rel))

    add_from(root)
    for legacy in extra_roots:
        if legacy.resolve() == root.resolve():
            continue
        add_from(legacy, Path("_Legacy_Import") / legacy.name)

    # Program workspace sources that should live in Dropbox
    workspace_sources = [
        (BASE_DIR / "docs" / "quotes" / "lily-315-sassafras", Path("_Program_Sync") / "docs/quotes/lily-315-sassafras"),
        (BASE_DIR / "iphone_files" / "Invoices", Path("_Program_Sync") / "iphone_files/Invoices"),
        (BASE_DIR / "business_standards", Path("_Program_Sync") / "business_standards"),
        (BASE_DIR / "document_templates", Path("_Program_Sync") / "document_templates"),
        (EXPORT_DIR, Path("_Program_Sync") / "exports"),
    ]
    for src, prefix in workspace_sources:
        add_from(src, prefix)

    # Non-standard folders inside root
    for child in root.iterdir():
        if child.is_dir() and child.name in NON_STANDARD_ROOT_FOLDERS:
            add_from(child, Path("_Legacy_Layout") / child.name)

    return items


def write_navigation_files(root: Path) -> None:
    ensure_dropbox_organization(root)
    start = root / "START_HERE_NAVIGATION.txt"
    start.write_text(
        "J & R Construction — Dropbox START HERE\n"
        "=========================================\n\n"
        f"Updated: {now_stamp()}\n\n"
        "This is your one Dropbox business root. Open folders by number:\n\n"
        "00_INBOX_To_File          New/scanned files to sort\n"
        "01_Jobs                   Active, completed, and estimate jobs\n"
        "02_Documents_Invoices_Estimates_Quotes   Customer invoices & quotes\n"
        "   └── Lily_315_Sassafras                 Lily stair + fence documents\n"
        "03_Receipts_Materials     Receipts and material records\n"
        "04_Photos_Evidence        Before / during / after job photos\n"
        "05_Helper_Pay_Workers     Helper pay records\n"
        "06_Bookkeeping_Taxes      Income, expenses, Schedule C\n"
        "07_Backups                Program and business backups\n"
        "08_Admin_Standards        Business standards and templates\n"
        "09_Archive                Old layouts and pre-reorg snapshots\n"
        "10_Logs                   Business log mirrors\n"
        "11_Exports                Program exports and reports\n"
        "12_Imports_ChatGPT        ChatGPT import files\n\n"
        "iPhone tip: Files app → Dropbox → this folder → START_HERE_NAVIGATION.txt\n",
        encoding="utf-8",
    )

    readme = root / "_JRC_DROPBOX_ORGANIZATION_README.txt"
    readme.write_text(
        "J & R Construction Dropbox organization\n\n"
        f"Updated: {now_stamp()}\n\n"
        "One-root rule: this folder is the single active J&R Dropbox business root.\n"
        "Legacy folders (Invoices2026 1.0, J and R Construction, JRC) are import-only.\n\n"
        "Standard folders:\n"
        + "\n".join(f"- {rel}" for rel in DROPBOX_ORGANIZATION_FOLDERS)
        + "\n\nIf you cannot find a file, check 09_Archive for pre-reorganization snapshots.\n",
        encoding="utf-8",
    )

    lily_readme = root / "02_Documents_Invoices_Estimates_Quotes" / "Lily_315_Sassafras" / "README_LILY_315.txt"
    lily_readme.parent.mkdir(parents=True, exist_ok=True)
    lily_readme.write_text(
        "Lily — 315 Sassafras Lane — customer documents\n\n"
        "Stair invoices: $1,000 each (friends & family)\n"
        "Fence estimate: two (2) four-foot (4 ft) gates\n\n"
        "Send-ready copies may also be in SEND_TO_LILY subfolder if synced from program.\n",
        encoding="utf-8",
    )

    inbox_readme = root / "00_INBOX_To_File" / "_README.txt"
    inbox_readme.write_text(
        "Drop new scans, photos, and unsorted business files here first.\n"
        "Run Dropbox reorganization from J&R Job Manager when ready to file them.\n",
        encoding="utf-8",
    )

    index = {
        "updated_at": now_stamp(),
        "root": str(root.resolve()),
        "standard_folders": DROPBOX_ORGANIZATION_FOLDERS,
        "customer_folders": {
            "Lily_315_Sassafras": "02_Documents_Invoices_Estimates_Quotes/Lily_315_Sassafras",
        },
        "legacy_candidates": DROPBOX_LEGACY_SOURCE_CANDIDATES,
    }
    (root / "JRC_ROOT_INDEX.json").write_text(json.dumps(index, indent=2), encoding="utf-8")


def reorganize_dropbox_business(root: Path | None = None, include_legacy: bool = True) -> ReorgReport:
    stamp = iso_stamp()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
        if root is None:
            root = resolve_dropbox_root(conn)
        root = ensure_dropbox_organization(Path(root))
        set_dropbox_root(conn, root)
    finally:
        conn.close()

    report = ReorgReport(root=root, stamp=stamp)
    inventory = inventory_tree(root)
    report.inventory_count = len(inventory)
    inventory_path = root / "07_Backups" / f"pre_reorg_inventory_{stamp}.json"
    inventory_path.write_text(json.dumps(inventory, indent=2), encoding="utf-8")

    report.snapshot_dir = snapshot_root(root, stamp)

    extra_roots = discover_legacy_roots() if include_legacy else []
    items = collect_files_to_organize(root, extra_roots)

    for source, rel in items:
        try:
            rel_posix = rel.as_posix()
            if source.is_relative_to(root):
                try:
                    rel_from_root = source.relative_to(root).as_posix()
                    if is_within_standard_tree(rel_from_root) and "/_Legacy_" not in rel_posix:
                        continue
                except ValueError:
                    pass

            dest_rel = classify_relative_destination(rel_posix, source.name)
            dest = root / dest_rel / source.name
            safe_copy_unique(source, dest, report)
        except Exception as exc:
            report.errors.append(f"{source}: {exc}")

    # Copy send-ready Lily bundle explicitly
    send_dir = BASE_DIR / "docs" / "quotes" / "lily-315-sassafras" / "SEND_TO_LILY"
    if send_dir.exists():
        lily_target = root / "02_Documents_Invoices_Estimates_Quotes" / "Lily_315_Sassafras" / "SEND_TO_LILY"
        for path in send_dir.iterdir():
            if path.is_file():
                safe_copy_unique(path, lily_target / path.name, report)

    write_navigation_files(root)

    report_path = root / "10_Logs" / f"dropbox_reorganization_report_{stamp}.txt"
    lines = [
        f"J&R Dropbox reorganization report — {now_stamp()}",
        f"Root: {root}",
        f"Inventory files before: {report.inventory_count}",
        f"Snapshot: {report.snapshot_dir}",
        f"Copied/placed: {len(report.copied)}",
        f"Skipped duplicates: {len(report.skipped_duplicate)}",
        f"Errors: {len(report.errors)}",
        "",
        "=== COPIED ===",
        *report.copied,
        "",
        "=== SKIPPED DUPLICATES ===",
        *report.skipped_duplicate,
        "",
        "=== ERRORS ===",
        *report.errors,
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # refresh log mirror if exports has one
    mirror = EXPORT_DIR / LOG_MIRROR_FILENAME
    if mirror.exists():
        shutil.copy2(mirror, root / "10_Logs" / LOG_MIRROR_FILENAME)

    return report


def main() -> int:
    report = reorganize_dropbox_business()
    print(f"Dropbox root: {report.root}")
    print(f"Pre-reorg inventory: {report.inventory_count} files")
    print(f"Snapshot saved: {report.snapshot_dir}")
    print(f"Files placed: {len(report.copied)}")
    print(f"Duplicates skipped: {len(report.skipped_duplicate)}")
    print(f"Errors: {len(report.errors)}")
    print(f"\nOpen on phone: Dropbox → {report.root.name} → START_HERE_NAVIGATION.txt")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
