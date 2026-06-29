# -*- coding: utf-8 -*-
"""
Densus + JRC Manager admin hub — monitoring data stored SEPARATE from business records.

All files live under data/densus_admin/ (not mixed with job/income CSV mirrors).
Purpose: admin-only snapshots of active users, session actions, and scan results.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]


def densus_admin_dir(install_dir: Path | None = None) -> Path:
    root = Path(install_dir or BASE_DIR)
    p = root / "data" / "densus_admin"
    p.mkdir(parents=True, exist_ok=True)
    (p / "snapshots").mkdir(exist_ok=True)
    (p / "session_actions").mkdir(exist_ok=True)
    return p


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _stamp_file() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def save_admin_snapshot(
    install_dir: Path,
    *,
    label: str,
    payload: Dict[str, Any],
    db_fn: Optional[Callable] = None,
) -> Path:
    """Write JSON snapshot to densus_admin/snapshots/ (never business Dropbox)."""
    admin = densus_admin_dir(install_dir)
    data = {"label": label, "saved_at": _stamp(), "payload": payload}
    if db_fn:
        try:
            data["active_users"] = fetch_active_sessions(db_fn)
            data["user_summary"] = fetch_user_summary(db_fn)
        except Exception as exc:
            data["db_error"] = str(exc)
    path = admin / "snapshots" / f"{label}_{_stamp_file()}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    (admin / "LAST_SNAPSHOT.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    append_session_log(install_dir, "snapshot", label, f"Saved {path.name}")
    return path


def append_session_log(install_dir: Path, action: str, target: str, detail: str, admin_user: str = "") -> Path:
    admin = densus_admin_dir(install_dir)
    line = {
        "time": _stamp(),
        "action": action,
        "target": target,
        "detail": detail,
        "admin": admin_user,
    }
    log_path = admin / "session_actions" / f"actions_{datetime.now().strftime('%Y-%m')}.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")
    return log_path


def fetch_active_sessions(db_fn: Callable) -> List[Dict[str, Any]]:
    conn = db_fn()
    cutoff = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        """
        SELECT os.session_id, os.username, os.role, os.ip_address, os.login_time, os.last_seen,
               os.active, os.revoked, u.id AS user_id, u.display_name, u.active AS user_active
        FROM online_sessions os
        LEFT JOIN users u ON u.username = os.username
        WHERE os.active = 1 AND os.revoked = 0
        ORDER BY os.last_seen DESC
        LIMIT 100
        """
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_user_summary(db_fn: Callable) -> Dict[str, Any]:
    conn = db_fn()
    total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM users WHERE active=1").fetchone()[0]
    by_role = conn.execute(
        "SELECT role, COUNT(*) AS c FROM users GROUP BY role ORDER BY c DESC"
    ).fetchall()
    pending = conn.execute(
        "SELECT COUNT(*) FROM account_requests WHERE status='Pending'"
    ).fetchone()[0]
    online = conn.execute(
        "SELECT COUNT(*) FROM online_sessions WHERE active=1 AND revoked=0"
    ).fetchone()[0]
    return {
        "total_users": total,
        "active_accounts": active,
        "online_sessions": online,
        "pending_requests": pending,
        "by_role": {r["role"]: r["c"] for r in by_role},
    }


def revoke_session(db_fn: Callable, session_id: str, reason: str, admin_username: str) -> Tuple[bool, str]:
    conn = db_fn()
    row = conn.execute(
        "SELECT username FROM online_sessions WHERE session_id=? AND active=1",
        (session_id,),
    ).fetchone()
    if not row:
        return False, "Session not found or already ended."
    conn.execute(
        "UPDATE online_sessions SET active=0, revoked=1, revoke_reason=? WHERE session_id=?",
        (reason or "Ended by admin via Densus JRC hub", session_id),
    )
    conn.commit()
    return True, f"Ended session for {row['username']}"


def load_last_snapshot(install_dir: Path) -> Optional[Dict[str, Any]]:
    p = densus_admin_dir(install_dir) / "LAST_SNAPSHOT.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_recent_snapshots(install_dir: Path, limit: int = 8) -> List[Path]:
    d = densus_admin_dir(install_dir) / "snapshots"
    files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def main() -> int:
    densus_admin_dir(BASE_DIR)
    print(f"Densus admin monitoring folder ready: {densus_admin_dir(BASE_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
