#!/usr/bin/env python3
"""Find Lily fence quote/invoice in Dropbox and bundle all customer-send PDFs."""

from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"
DB_PATH = DATA_DIR / "jr_business.db"
DOCS_DIR = BASE_DIR / "docs" / "quotes" / "lily-315-sassafras"
SEND_DIR = DOCS_DIR / "SEND_TO_LILY"
DEFAULT_DROPBOX_ROOT = BASE_DIR / "dropbox_business"
LOG_MIRROR_FILENAME = "JRC_Business_Log_Latest.txt"
DROPBOX_DOCS_ROOT = "02_Documents_Invoices_Estimates_Quotes"
LILY_DROPBOX_DIRNAME = "Lily_315_Sassafras"

FENCE_KEYWORDS = ("fence", "fencing", "gate", "picket", "privacy")
LILY_KEYWORDS = ("lily", "315", "sassafras")
DOC_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".html", ".htm"}

STAIR_SEND_FILES = [
    (
        "INV-JRC-JOB-315-LILY-STAIR-SET-01-001",
        "Lily_315_Sassafras_Stair_Set_1_CUSTOMER_INVOICE.pdf",
    ),
    (
        "INV-JRC-JOB-315-LILY-STAIR-SET-02-001",
        "Lily_315_Sassafras_Stair_Set_2_CUSTOMER_INVOICE.pdf",
    ),
]
FENCE_SEND_NAME = "Lily_315_Sassafras_Fence_CUSTOMER_ESTIMATE.pdf"


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %I:%M %p")


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def dropbox_roots(conn: sqlite3.Connection) -> list[Path]:
    roots: list[Path] = []
    configured = get_setting(conn, "dropbox_folder", "").strip()
    if configured:
        roots.append(Path(configured).expanduser())
    env_root = os.environ.get("JRC_DROPBOX_FOLDER", "").strip()
    if env_root:
        roots.append(Path(env_root).expanduser())
    roots.append(DEFAULT_DROPBOX_ROOT)

    home = Path.home()
    legacy_names = ["Invoices2026 1.0", "J and R Construction", "JRC"]
    for legacy in legacy_names:
        for parent in [home / "Dropbox", home / "OneDrive" / "Desktop", home / "Documents"]:
            candidate = parent / legacy
            if candidate.exists():
                roots.append(candidate)

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve()) if root.exists() else str(root)
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def score_fence_candidate(path: Path) -> int:
    name = path.name.lower()
    score = 0
    if any(k in name for k in FENCE_KEYWORDS):
        score += 4
    if any(k in name for k in LILY_KEYWORDS):
        score += 4
    if "inv-" in name or "est-" in name or "quote" in name or "invoice" in name or "estimate" in name:
        score += 2
    if path.suffix.lower() in DOC_EXTENSIONS:
        score += 1
  # deprioritize stair-only files
    if "stair" in name and "fence" not in name:
        score -= 6
    return score


def find_fence_quote(roots: list[Path]) -> tuple[Path | None, list[str]]:
    searched: list[str] = []
    candidates: list[tuple[int, Path]] = []

    for root in roots:
        searched.append(str(root))
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in DOC_EXTENSIONS:
                continue
            score = score_fence_candidate(path)
            if score >= 5:
                candidates.append((score, path))

    if not candidates:
        return None, searched

    candidates.sort(key=lambda item: (item[0], item[1].stat().st_mtime), reverse=True)
    return candidates[0][1], searched


def latest_stair_pdf(doc_no: str) -> Path | None:
    matches = sorted(DOCS_DIR.glob(f"{doc_no}_*.pdf"))
    if matches:
        return matches[-1]
    matches = sorted((EXPORT_DIR).glob(f"{doc_no}_*.pdf"))
    return matches[-1] if matches else None


def mirror_business_log(conn: sqlite3.Connection, dropbox_root: Path, lines: list[str]) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        "SELECT timestamp, category, entry FROM business_log ORDER BY id DESC LIMIT 250"
    ).fetchall()
    content = [
        "J and R Construction Manager business log mirror",
        f"Updated: {now_stamp()}",
        "",
    ]
    for timestamp, category, entry in reversed(rows):
        content.append(f"[{timestamp}] {category}: {entry}")
    mirror_path = EXPORT_DIR / LOG_MIRROR_FILENAME
    mirror_path.write_text("\n".join(content) + "\n", encoding="utf-8")
    if dropbox_root.exists():
        for rel in ("10_Logs", ""):
            target_dir = dropbox_root / rel if rel else dropbox_root
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(mirror_path, target_dir / LOG_MIRROR_FILENAME)
    return mirror_path


def log_entry(conn: sqlite3.Connection, category: str, entry: str) -> None:
    conn.execute(
        "INSERT INTO business_log(timestamp, category, entry) VALUES(?,?,?)",
        (now_stamp(), category, entry),
    )
    conn.commit()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS business_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            category TEXT,
            entry TEXT
        )
        """
    )
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()


def bundle_stair_invoices(dropbox_root: Path) -> list[Path]:
    SEND_DIR.mkdir(parents=True, exist_ok=True)
    dropbox_target = dropbox_root / DROPBOX_DOCS_ROOT / LILY_DROPBOX_DIRNAME
    dropbox_target.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    for doc_no, send_name in STAIR_SEND_FILES:
        source = latest_stair_pdf(doc_no)
        if source is None:
            raise FileNotFoundError(f"Missing stair invoice PDF for {doc_no}")
        send_path = SEND_DIR / send_name
        dropbox_path = dropbox_target / send_name
        shutil.copy2(source, send_path)
        shutil.copy2(source, dropbox_path)
        saved.extend([send_path, dropbox_path])
    return saved


def latest_generated_fence_estimate() -> Path | None:
    matches = sorted(DOCS_DIR.glob("EST-JRC-JOB-315-LILY-FENCE-001_*.pdf"))
    return matches[-1] if matches else None


def bundle_generated_fence_quote(dropbox_root: Path) -> list[Path] | None:
    source = latest_generated_fence_estimate()
    if source is None:
        return None
    SEND_DIR.mkdir(parents=True, exist_ok=True)
    dropbox_target = dropbox_root / DROPBOX_DOCS_ROOT / LILY_DROPBOX_DIRNAME
    dropbox_target.mkdir(parents=True, exist_ok=True)
    send_path = SEND_DIR / "Lily_315_Sassafras_Fence_CUSTOMER_ESTIMATE.pdf"
    dropbox_path = dropbox_target / "Lily_315_Sassafras_Fence_CUSTOMER_ESTIMATE.pdf"
    shutil.copy2(source, send_path)
    shutil.copy2(source, dropbox_path)
    return [send_path, dropbox_path]


def main() -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_schema(conn)
        roots = dropbox_roots(conn)
        dropbox_root = roots[0] if roots else DEFAULT_DROPBOX_ROOT
        if dropbox_root.exists() and not get_setting(conn, "dropbox_folder", "").strip():
            conn.execute(
                "INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("dropbox_folder", str(dropbox_root.resolve())),
            )
            conn.commit()

        stair_paths = bundle_stair_invoices(dropbox_root)
        fence_paths: list[Path] = []
        fence_source: Path | None = None
        searched: list[str] = []

        log_entry(
            conn,
            "Document",
            "Bundled Lily / 315 Sassafras stair customer invoices for send: "
            "INV-JRC-JOB-315-LILY-STAIR-SET-01-001 and INV-JRC-JOB-315-LILY-STAIR-SET-02-001 "
            f"into {SEND_DIR} and Dropbox {DROPBOX_DOCS_ROOT}/{LILY_DROPBOX_DIRNAME}.",
        )

        generated_fence = bundle_generated_fence_quote(dropbox_root)
        if generated_fence:
            fence_paths = generated_fence
            log_entry(
                conn,
                "Document",
                "Bundled generated Lily fence customer estimate with two 4 ft gates: "
                f"{SEND_DIR / FENCE_SEND_NAME}",
            )
        else:
            fence_source, searched = find_fence_quote(roots)
            if fence_source:
                SEND_DIR.mkdir(parents=True, exist_ok=True)
                dropbox_target = dropbox_root / DROPBOX_DOCS_ROOT / LILY_DROPBOX_DIRNAME
                dropbox_target.mkdir(parents=True, exist_ok=True)
                send_path = SEND_DIR / FENCE_SEND_NAME
                dropbox_path = dropbox_target / FENCE_SEND_NAME
                shutil.copy2(fence_source, send_path)
                shutil.copy2(fence_source, dropbox_path)
                fence_paths = [send_path, dropbox_path]
                log_entry(
                    conn,
                    "Document",
                    "Found existing Lily fence quote/invoice in Dropbox and copied customer send copy: "
                    f"{fence_source} -> {SEND_DIR / FENCE_SEND_NAME}",
                )
            else:
                log_entry(
                    conn,
                    "Document",
                    "Lily fence quote not found in searchable Dropbox paths from this environment. "
                    "Run tools/generate_lily_315_fence_estimate.py to create the customer estimate. "
                    "Searched: "
                    + "; ".join(searched),
                )

        mirror_business_log(conn, dropbox_root, [])

        print("SEND TO LILY folder:")
        for path in sorted(SEND_DIR.glob("*")):
            print(f"  {path}")
        print("\nDropbox customer folder:")
        target = dropbox_root / DROPBOX_DOCS_ROOT / LILY_DROPBOX_DIRNAME
        if target.exists():
            for path in sorted(target.glob("*")):
                print(f"  {path}")
        if fence_paths:
            print(f"\nFence customer copy ready: {fence_paths[0]}")
            return 0
        if fence_source:
            print(f"\nFence source used: {fence_source}")
            return 0
        print("\nFence quote: NOT FOUND. Run tools/generate_lily_315_fence_estimate.py")
        if searched:
            print("Searched roots:")
            for root in searched:
                print(f"  - {root}")
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
