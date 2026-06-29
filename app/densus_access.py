"""Owner-approved Densus access — download and use gated for listed admins only."""
from __future__ import annotations

import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.role_utils import DEFAULT_OWNER_USERNAME, is_admin_role

BASE_DIR = Path(__file__).resolve().parents[1]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS densus_access_grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    status TEXT DEFAULT 'Pending',
    request_note TEXT,
    admin_notes TEXT,
    request_ip TEXT,
    requested_at TEXT,
    reviewed_at TEXT,
    reviewed_by TEXT,
    last_download_at TEXT,
    UNIQUE(user_id)
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(SCHEMA_SQL)
    conn.commit()


def is_primary_owner(username: str) -> bool:
    return (username or "").strip().lower() == DEFAULT_OWNER_USERNAME.lower()


def has_densus_access(
    conn: sqlite3.Connection,
    user_id: int | None,
    username: str,
    role: str,
) -> bool:
    """Owner always has access; other admins need an Approved grant."""
    if not is_admin_role(role):
        return False
    if is_primary_owner(username):
        return True
    if not user_id:
        return False
    ensure_schema(conn)
    row = conn.execute(
        "SELECT status FROM densus_access_grants WHERE user_id=?",
        (int(user_id),),
    ).fetchone()
    return bool(row and str(row["status"] if isinstance(row, sqlite3.Row) else row[0]) == "Approved")


def access_status(conn: sqlite3.Connection, user_id: int | None, username: str, role: str) -> str:
    if not is_admin_role(role):
        return "not_admin"
    if is_primary_owner(username):
        return "owner"
    if not user_id:
        return "none"
    ensure_schema(conn)
    row = conn.execute(
        "SELECT status FROM densus_access_grants WHERE user_id=?",
        (int(user_id),),
    ).fetchone()
    if not row:
        return "none"
    return str(row["status"] if isinstance(row, sqlite3.Row) else row[0])


def pending_count(conn: sqlite3.Connection) -> int:
    ensure_schema(conn)
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM densus_access_grants WHERE status='Pending'"
        ).fetchone()[0]
    )


def submit_access_request(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    username: str,
    note: str,
    request_ip: str,
    now_iso: Callable[[], str],
) -> Tuple[bool, str]:
    ensure_schema(conn)
    if is_primary_owner(username):
        return True, "Owner account always has Densus access."
    existing = conn.execute(
        "SELECT id, status FROM densus_access_grants WHERE user_id=?",
        (user_id,),
    ).fetchone()
    if existing:
        st = existing["status"] if isinstance(existing, sqlite3.Row) else existing[1]
        if st == "Approved":
            return True, "You already have approved Densus access."
        if st == "Pending":
            return False, "Your Densus access request is already pending owner approval."
        if st == "Denied":
            conn.execute(
                """UPDATE densus_access_grants SET status='Pending', request_note=?, request_ip=?,
                   requested_at=?, reviewed_at=NULL, reviewed_by=NULL, admin_notes=NULL WHERE user_id=?""",
                (note[:500], request_ip, now_iso(), user_id),
            )
            conn.commit()
            return True, "Densus access request resubmitted for owner review."
        if st == "Revoked":
            conn.execute(
                """UPDATE densus_access_grants SET status='Pending', request_note=?, request_ip=?,
                   requested_at=?, reviewed_at=NULL, reviewed_by=NULL, admin_notes=NULL WHERE user_id=?""",
                (note[:500], request_ip, now_iso(), user_id),
            )
            conn.commit()
            return True, "Densus access request submitted after prior revoke."
    conn.execute(
        """INSERT INTO densus_access_grants
           (user_id, username, status, request_note, request_ip, requested_at)
           VALUES (?, ?, 'Pending', ?, ?, ?)""",
        (user_id, username, note[:500], request_ip, now_iso()),
    )
    conn.commit()
    return True, "Densus access request sent to the J&R owner for approval."


def review_grant(
    conn: sqlite3.Connection,
    grant_id: int,
    *,
    decision: str,
    reviewer: str,
    notes: str,
    now_iso: Callable[[], str],
) -> Tuple[bool, str]:
    if not is_primary_owner(reviewer):
        return False, "Only the J&R owner account can approve Densus access."
    ensure_schema(conn)
    row = conn.execute("SELECT * FROM densus_access_grants WHERE id=?", (grant_id,)).fetchone()
    if not row:
        return False, "Request not found."
    if decision not in {"Approved", "Denied", "Revoked"}:
        return False, "Invalid decision."
    conn.execute(
        """UPDATE densus_access_grants SET status=?, reviewed_at=?, reviewed_by=?, admin_notes=?
           WHERE id=?""",
        (decision, now_iso(), reviewer, notes[:500], grant_id),
    )
    conn.commit()
    uname = row["username"] if isinstance(row, sqlite3.Row) else row[2]
    return True, f"Densus access {decision.lower()} for {uname}."


def list_grants(conn: sqlite3.Connection, status: str | None = None, limit: int = 50) -> List[Dict[str, Any]]:
    ensure_schema(conn)
    if status:
        rows = conn.execute(
            "SELECT * FROM densus_access_grants WHERE status=? ORDER BY id DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM densus_access_grants ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def record_download(conn: sqlite3.Connection, user_id: int, now_iso: Callable[[], str]) -> None:
    ensure_schema(conn)
    conn.execute(
        "UPDATE densus_access_grants SET last_download_at=? WHERE user_id=?",
        (now_iso(), user_id),
    )
    conn.commit()


def resolve_densus_package_source() -> Optional[Path]:
    home = Path.home()
    candidates = [
        home / "Documents" / "JRC" / "Densus",
        BASE_DIR.parent / "Densus",
        Path(os.environ.get("DENSUS_PACKAGE_DIR", "")),
    ]
    for p in candidates:
        if not p or not p.exists():
            continue
        if (p / "app" / "densus_main.py").exists() or (p / "!!! START DENSUS INSTALL.vbs").exists():
            return p.resolve()
    return None


def create_densus_download_zip() -> Tuple[Optional[Path], str]:
    source = resolve_densus_package_source()
    if not source:
        return None, "Densus install source not found on this PC (Documents\\JRC\\Densus)."
    skip = {".venv", "venv", "data", "__pycache__", ".git", "node_modules"}
    fd, raw = tempfile.mkstemp(suffix=".zip", prefix="densus_pkg_")
    os.close(fd)
    out = Path(raw)
    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in source.rglob("*"):
                if not f.is_file():
                    continue
                rel = f.relative_to(source)
                if any(part in skip for part in rel.parts):
                    continue
                zf.write(f, arcname=str(Path("Densus") / rel))
        return out, f"Packaged from {source}"
    except Exception as exc:
        if out.exists():
            out.unlink(missing_ok=True)
        return None, str(exc)
