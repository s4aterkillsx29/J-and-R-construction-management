# -*- coding: utf-8 -*-
"""Root device agreement + rooted live session tracking (non-owner users)."""
from __future__ import annotations

import platform
import sqlite3
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from app.role_utils import DEFAULT_OWNER_USERNAME

AGREEMENT_FIELD = "root_device_agreement"
AGREEMENT_TEXT = (
    "I agree that J & R Construction owner/admin may identify and track this device "
    "and my live session for security, audit, and program administration."
)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_owner_account(user: Dict[str, Any] | sqlite3.Row | None) -> bool:
    if not user:
        return False
    if isinstance(user, sqlite3.Row):
        user = dict(user)
    if int(user.get("owner_account") or 0):
        return True
    username = (user.get("username") or "").strip().lower()
    return username == DEFAULT_OWNER_USERNAME.lower()


def agreement_checked(form_value: Optional[str]) -> bool:
    return (form_value or "").strip() in {"1", "on", "yes", "true"}


def ensure_root_session_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS rooted_live_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL UNIQUE,
            user_id INTEGER,
            username TEXT NOT NULL,
            role TEXT,
            ip_address TEXT,
            user_agent TEXT,
            device_label TEXT,
            device_fingerprint TEXT,
            pc_hostname TEXT,
            agreement_at TEXT NOT NULL,
            login_source TEXT,
            login_time TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            ended_at TEXT,
            notes TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_rooted_live_active ON rooted_live_sessions(active, last_seen);
        CREATE INDEX IF NOT EXISTS idx_rooted_live_user ON rooted_live_sessions(username, last_seen);
        """
    )
    for stmt in (
        "ALTER TABLE online_sessions ADD COLUMN root_device_agreed INTEGER DEFAULT 0",
        "ALTER TABLE online_sessions ADD COLUMN session_rooted INTEGER DEFAULT 0",
        "ALTER TABLE online_sessions ADD COLUMN root_agreement_at TEXT",
    ):
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    conn.commit()


def record_session_root_tracking(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    user: Dict[str, Any] | sqlite3.Row,
    ip_address: str,
    user_agent: str,
    device_label: str,
    device_fingerprint: str,
    root_agreed: bool,
    login_source: str,
    log_security_event: Callable[..., None],
) -> Dict[str, Any]:
    """Log agreement on all logins; full rooted tracking for non-owner users only."""
    ensure_root_session_schema(conn)
    owner = is_owner_account(user)
    user_id = int(user["id"])
    username = user["username"]
    role = user.get("role") if hasattr(user, "get") else user["role"]
    ts = _now()
    hostname = platform.node() or "unknown"
    agreed_flag = 1 if root_agreed else 0
    rooted_flag = 0 if owner else (1 if root_agreed else 0)

    conn.execute(
        """
        UPDATE online_sessions
        SET root_device_agreed=?, session_rooted=?, root_agreement_at=?
        WHERE session_id=?
        """,
        (agreed_flag, rooted_flag, ts if root_agreed else None, session_id),
    )

    result = {
        "owner": owner,
        "rooted": bool(rooted_flag),
        "agreed": bool(root_agreed),
    }

    if owner:
        if root_agreed:
            log_security_event(
                "owner_login_agreement",
                username,
                f"Owner signed device/session policy on {device_label} from {ip_address}",
                "OK",
            )
        return result

    if not root_agreed:
        log_security_event(
            "root_agreement_missing",
            username,
            "Non-owner login without root device agreement",
            "WARN",
        )
        return result

    conn.execute(
        """
        INSERT INTO rooted_live_sessions
        (session_id, user_id, username, role, ip_address, user_agent, device_label,
         device_fingerprint, pc_hostname, agreement_at, login_source, login_time, last_seen, active)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1)
        ON CONFLICT(session_id) DO UPDATE SET
            last_seen=excluded.last_seen,
            active=1,
            ip_address=excluded.ip_address,
            user_agent=excluded.user_agent
        """,
        (
            session_id,
            user_id,
            username,
            role,
            ip_address,
            user_agent,
            device_label,
            device_fingerprint,
            hostname,
            ts,
            login_source,
            ts,
            ts,
        ),
    )
    log_security_event(
        "rooted_session_started",
        username,
        f"Rooted live session on {device_label} ({hostname}) from {ip_address} via {login_source}",
        "OK",
    )
    return result


def touch_rooted_session(conn: sqlite3.Connection, session_id: str) -> None:
    if not session_id:
        return
    ensure_root_session_schema(conn)
    ts = _now()
    conn.execute(
        "UPDATE rooted_live_sessions SET last_seen=?, active=1 WHERE session_id=? AND active=1",
        (ts, session_id),
    )


def end_rooted_session(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    reason: str = "logout",
    log_security_event: Optional[Callable[..., None]] = None,
) -> None:
    ensure_root_session_schema(conn)
    row = conn.execute(
        "SELECT username FROM rooted_live_sessions WHERE session_id=? AND active=1",
        (session_id,),
    ).fetchone()
    if not row:
        return
    ts = _now()
    conn.execute(
        """
        UPDATE rooted_live_sessions
        SET active=0, ended_at=?, notes=?
        WHERE session_id=?
        """,
        (ts, reason, session_id),
    )
    if log_security_event:
        log_security_event(
            "rooted_session_ended",
            row["username"],
            f"Rooted session ended: {reason}",
            "INFO",
        )


def list_rooted_sessions(conn: sqlite3.Connection, *, limit: int = 100) -> list[dict]:
    ensure_root_session_schema(conn)
    rows = conn.execute(
        """
        SELECT * FROM rooted_live_sessions
        ORDER BY active DESC, last_seen DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def register_root_session_routes(
    app,
    *,
    db_fn: Callable,
    login_required: Callable,
    layout: Callable,
) -> None:
    import html

    @app.route("/admin/rooted-sessions")
    @login_required("view_admin")
    def admin_rooted_sessions():
        conn = db_fn()
        rows = list_rooted_sessions(conn, limit=150)
        trs = "".join(
            f"<tr><td><b>{html.escape(r['username'])}</b></td>"
            f"<td>{html.escape(r.get('role') or '')}</td>"
            f"<td>{html.escape(r.get('device_label') or '')}<br>"
            f"<span class='muted'>{html.escape((r.get('user_agent') or '')[:70])}</span></td>"
            f"<td>{html.escape(r.get('ip_address') or '')}<br>"
            f"<span class='muted'>{html.escape(r.get('pc_hostname') or '')}</span></td>"
            f"<td>{html.escape(r.get('login_time') or '')}</td>"
            f"<td>{html.escape(r.get('last_seen') or '')}</td>"
            f"<td>{'Active' if r.get('active') else 'Ended'}</td></tr>"
            for r in rows
        )
        body = f"""
        <div class="card"><h2>Rooted Live Sessions</h2>
        <p class="muted">Non-owner users who agreed to owner device/session tracking at sign-in.
        Owner sessions are not rooted here.</p>
        <table><tr><th>User</th><th>Role</th><th>Device</th><th>IP / PC</th>
        <th>Login</th><th>Last seen</th><th>Status</th></tr>
        {trs or '<tr><td colspan=7>No rooted sessions logged yet</td></tr>'}</table>
        <p><a class="btn btn2" href="/admin">Back to Admin</a>
        <a class="btn btn2" href="/admin/live-sessions">All online sessions</a></p></div>
        """
        return layout("Rooted Sessions", body, "admin")
