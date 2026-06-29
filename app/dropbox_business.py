"""Dropbox business folder — read, index, sensitive backup push, live health checks."""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sqlite3
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("JRC_DATA_DIR", str(BASE_DIR / "data"))).expanduser()
EXPORT_DIR = Path(os.environ.get("JRC_EXPORT_DIR", str(BASE_DIR / "exports"))).expanduser()
EVIDENCE_DIR = Path(os.environ.get("JRC_EVIDENCE_DIR", str(BASE_DIR / "evidence"))).expanduser()
BACKUP_DIR = Path(os.environ.get("JRC_BACKUP_DIR", str(BASE_DIR / "backups"))).expanduser()
CHATGPT_IMPORTS_DIR = Path(os.environ.get("JRC_CHATGPT_IMPORTS_DIR", str(BASE_DIR / "chatgpt_imports"))).expanduser()
DB_PATH = Path(os.environ.get("JRC_DB_PATH", str(DATA_DIR / "jr_business.db"))).expanduser()

SENSITIVE_SUBDIR = "JRC-Sensitive-Backups"


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    try:
        row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row and row["value"] is not None else default
    except Exception:
        return default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", (key, value or ""))
    conn.commit()


def _desktop_dir() -> Path:
    try:
        from app.install_paths import _desktop_dir as _d
        return _d()
    except Exception:
        home = Path.home()
        for candidate in (home / "OneDrive" / "Desktop", home / "Desktop"):
            if candidate.exists():
                return candidate
        return home / "Desktop"


def discover_dropbox_presets() -> List[Tuple[str, Path]]:
    home = Path.home()
    desk = _desktop_dir()
    presets: List[Tuple[str, Path]] = [
        ("Desktop — J and R Construction Manager (local program)", desk / "J and R Construction Manager"),
        ("Desktop — J and R Construction", desk / "J and R Construction"),
        ("Desktop — JRC", desk / "JRC"),
        ("J and R Construction", home / "Dropbox" / "J and R Construction"),
        ("JRC", home / "Dropbox" / "JRC"),
        ("Invoices2026 1.0", home / "Dropbox" / "Invoices2026 1.0"),
        ("Dropbox All Files — JRC", home / "Dropbox" / "All Files" / "JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22" / "JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22"),
        ("dropbox-records", home / "Dropbox" / "dropbox-records"),
    ]
    return [(name, p) for name, p in presets if p.exists()]


def get_dropbox_folder(conn: sqlite3.Connection) -> str:
    folder = get_setting(conn, "dropbox_folder", "").strip()
    if folder and Path(folder).exists():
        return folder
    try:
        from app.install_paths import owner_install_dir
        owner = owner_install_dir()
        if owner.exists():
            set_setting(conn, "dropbox_folder", str(owner))
            return str(owner)
    except Exception:
        pass
    for _, path in discover_dropbox_presets():
        set_setting(conn, "dropbox_folder", str(path))
        return str(path)
    return folder


def ensure_dropbox_file_source(conn: sqlite3.Connection) -> Optional[str]:
    folder = get_dropbox_folder(conn)
    if not folder or not Path(folder).exists():
        return None
    conn.execute(
        """CREATE TABLE IF NOT EXISTS file_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT,
            source_type TEXT,
            folder_path TEXT,
            active INTEGER DEFAULT 1,
            notes TEXT,
            created_at TEXT
        )"""
    )
    label = "Dropbox Business Folder"
    existing = conn.execute(
        "SELECT id FROM file_sources WHERE label=? OR folder_path=?", (label, folder)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE file_sources SET folder_path=?, source_type='dropbox-local', active=1 WHERE id=?",
            (folder, existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO file_sources (label, source_type, folder_path, active, notes, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (label, "dropbox-local", folder, 1, "Owner Dropbox-synced business backup source.", _now()),
        )
    conn.commit()
    return folder


def build_backup_zip(target: Path, include_db: bool = True) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        if include_db and DB_PATH.exists():
            z.write(DB_PATH, Path("data") / DB_PATH.name)
        for folder, arc_prefix in [
            (EXPORT_DIR, "exports"),
            (EVIDENCE_DIR, "evidence"),
            (BACKUP_DIR, "backups"),
            (CHATGPT_IMPORTS_DIR, "chatgpt_imports"),
        ]:
            if folder.exists():
                for p in folder.rglob("*"):
                    if p.is_file():
                        z.write(p, Path(arc_prefix) / p.relative_to(folder))
        z.writestr(
            "BACKUP_MANIFEST.txt",
            f"J&R Construction Manager sensitive business backup\nCreated: {_now()}\nDB: {DB_PATH.name}\n",
        )
    return target


def sync_backup_to_dropbox(conn: sqlite3.Connection, base_dir: Optional[Path] = None) -> Tuple[bool, str, Optional[Path]]:
    folder = ensure_dropbox_file_source(conn)
    if not folder:
        return False, "Dropbox business folder not configured or not found on this PC.", None
    dropbox = Path(folder)
    sensitive = dropbox / SENSITIVE_SUBDIR
    sensitive.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    target = sensitive / f"JRC_Business_Backup_{stamp}.zip"
    build_backup_zip(target)
    set_setting(conn, "dropbox_last_backup", _now())
    set_setting(conn, "dropbox_last_backup_file", str(target))
    manifest = {
        "last_backup": _now(),
        "file": str(target),
        "dropbox_folder": folder,
        "indexed_sources": conn.execute("SELECT COUNT(*) FROM file_sources WHERE active=1").fetchone()[0],
    }
    (dropbox / "JRC_pipeline_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return True, f"Sensitive business backup pushed to Dropbox: {target.name}", target


def push_business_exports_to_dropbox(conn: sqlite3.Connection) -> Tuple[int, str]:
    folder = get_dropbox_folder(conn)
    if not folder or not Path(folder).exists():
        return 0, "Dropbox folder missing."
    dest = Path(folder) / SENSITIVE_SUBDIR / "exports_mirror"
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    if EXPORT_DIR.exists():
        for src in EXPORT_DIR.glob("*"):
            if src.is_file():
                shutil.copy2(src, dest / src.name)
                count += 1
    set_setting(conn, "dropbox_exports_mirror_at", _now())
    return count, f"Mirrored {count} export file(s) to Dropbox sensitive folder."


def run_dropbox_live_check(conn: sqlite3.Connection, base_dir: Optional[Path] = None) -> Dict[str, Any]:
    base_dir = base_dir or BASE_DIR
    report: Dict[str, Any] = {
        "time": _now(),
        "ok": True,
        "checks": [],
        "dropbox_folder": "",
        "preset_folders_found": [str(p) for _, p in discover_dropbox_presets()],
    }

    def add(level: str, name: str, detail: str) -> None:
        report["checks"].append({"level": level, "name": name, "detail": detail})
        if level in ("ERROR", "WARN"):
            report["ok"] = False if level == "ERROR" else report["ok"]

    folder = get_dropbox_folder(conn)
    report["dropbox_folder"] = folder
    if not folder:
        add("ERROR", "dropbox_folder", "No Dropbox business folder configured.")
    elif not Path(folder).exists():
        add("ERROR", "dropbox_path", f"Configured folder missing: {folder}")
    else:
        add("OK", "dropbox_path", f"Folder exists: {folder}")
        writable = Path(folder) / SENSITIVE_SUBDIR
        try:
            writable.mkdir(parents=True, exist_ok=True)
            test = writable / ".jrc_write_test"
            test.write_text("ok", encoding="utf-8")
            test.unlink(missing_ok=True)
            add("OK", "dropbox_write", "Can write sensitive backup subfolder.")
        except Exception as exc:
            add("ERROR", "dropbox_write", f"Cannot write to Dropbox folder: {exc}")

    ensure_dropbox_file_source(conn)
    sources = conn.execute(
        "SELECT label, folder_path, active FROM file_sources WHERE source_type LIKE '%dropbox%' OR label LIKE '%Dropbox%'"
    ).fetchall()
    if not sources:
        add("WARN", "file_sources", "No Dropbox file sources registered.")
    else:
        for s in sources:
            path = s["folder_path"] or ""
            if path and Path(path).exists():
                add("OK", "source_index", f"{s['label']}: readable")
            else:
                add("WARN", "source_index", f"{s['label']}: path missing ({path})")

    last = get_setting(conn, "dropbox_last_backup", "")
    if last:
        add("OK", "last_backup", f"Last Dropbox backup: {last}")
    else:
        add("WARN", "last_backup", "No Dropbox backup pushed yet. Run backup sync before live test.")

    indexed = conn.execute("SELECT COUNT(*) FROM file_index").fetchone()[0]
    add("OK", "indexed_files", f"{indexed} files indexed from all sources.")

    report["policy"] = (
        "Dropbox is the business file backup source (sensitive). "
        "SQLite database is backed up into Dropbox — not live-shared for simultaneous edits."
    )
    return report
