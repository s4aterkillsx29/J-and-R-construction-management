"""Desktop active session — shared by Tk program, web server, and features."""
from __future__ import annotations

import atexit
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

IDLE_MINUTES = int(os.environ.get("JRC_SESSION_IDLE_MINUTES", os.environ.get("JRC_SESSION_TIMEOUT_MINUTES", "30")))
SESSION_FILE = "desktop_active_session.json"


def _base_dir(base: Path | None = None) -> Path:
    if base:
        return Path(base).resolve()
    return Path(__file__).resolve().parents[1]


def _db_path(base: Path) -> Path:
    env = os.environ.get("JRC_DB_PATH", "").strip()
    if env:
        return Path(env).expanduser()
    return base / "data" / "jr_business.db"


def _session_path(base: Path) -> Path:
    return base / "data" / SESSION_FILE


def _connect(base: Path) -> sqlite3.Connection:
    db = _db_path(base)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def ensure_session_schema(base: Path | None = None) -> None:
    """Ensure DB tables/columns exist before session writes."""
    root = _base_dir(base)
    try:
        from app.network_server import init_db

        init_db()
    except Exception:
        pass
    try:
        from app.db_health import ensure_database_healthy

        ensure_database_healthy(_db_path(root), log_dir=root / "logs")
    except Exception:
        pass
    try:
        with _connect(root) as conn:
            for stmt in (
                "ALTER TABLE online_sessions ADD COLUMN client_device_fingerprint TEXT",
                "ALTER TABLE online_sessions ADD COLUMN client_device_label TEXT",
                "ALTER TABLE online_sessions ADD COLUMN device_trust_status TEXT",
                "ALTER TABLE online_sessions ADD COLUMN revoked INTEGER DEFAULT 0",
                "ALTER TABLE online_sessions ADD COLUMN revoke_reason TEXT",
            ):
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    pass
            conn.commit()
    except Exception:
        pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _load_file(base: Path) -> dict[str, Any] | None:
    path = _session_path(base)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_file(base: Path, payload: dict[str, Any]) -> None:
    path = _session_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _clear_file(base: Path) -> None:
    path = _session_path(base)
    try:
        if path.is_file():
            path.unlink()
    except Exception:
        pass


def create_desktop_session(user: dict[str, Any], base: Path | None = None, *, source: str = "desktop") -> dict[str, Any]:
    """Create active session row + desktop session file."""
    root = _base_dir(base)
    ensure_session_schema(root)
    sid = str(uuid.uuid4())
    now = _now_iso()
    ts = time.time()
    user_id = int(user["id"])
    username = str(user.get("username") or "")
    role = str(user.get("role") or "viewer")
    try:
        from app.role_utils import normalize_role_for_session

        role = normalize_role_for_session(role)
    except Exception:
        pass
    with _connect(root) as conn:
        conn.execute(
            """INSERT INTO online_sessions
               (session_id, user_id, username, role, ip_address, user_agent, trusted_device_id,
                client_device_fingerprint, client_device_label, device_trust_status,
                login_time, last_seen, active, revoked, revoke_reason)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,0,NULL)""",
            (
                sid,
                user_id,
                username,
                role,
                "127.0.0.1",
                f"JRC Desktop ({source})",
                "",
                "",
                "Desktop Program",
                "desktop_trusted",
                now,
                now,
            ),
        )
        conn.execute("UPDATE users SET last_login=? WHERE id=?", (now, user_id))
        conn.commit()
    payload = {
        "sid": sid,
        "user_id": user_id,
        "username": username,
        "role": role,
        "login_time": now,
        "last_activity": ts,
        "idle_minutes": IDLE_MINUTES,
        "source": source,
    }
    _save_file(root, payload)
    try:
        from app.local_login_gate import set_last_desktop_login

        set_last_desktop_login(user)
    except Exception:
        pass
    return payload


def touch_desktop_session(base: Path | None = None) -> bool:
    """Refresh idle timer + online_sessions.last_seen."""
    root = _base_dir(base)
    data = _load_file(root)
    if not data or not data.get("sid"):
        return False
    data["last_activity"] = time.time()
    _save_file(root, data)
    try:
        with _connect(root) as conn:
            conn.execute(
                "UPDATE online_sessions SET last_seen=?, active=1, revoked=0 WHERE session_id=?",
                (_now_iso(), data["sid"]),
            )
            conn.commit()
    except Exception:
        pass
    return True


def revoke_desktop_session(base: Path | None = None, reason: str = "Signed out") -> None:
    root = _base_dir(base)
    data = _load_file(root)
    sid = data.get("sid") if data else None
    if sid:
        try:
            with _connect(root) as conn:
                conn.execute(
                    "UPDATE online_sessions SET active=0, revoked=1, revoke_reason=?, last_seen=? WHERE session_id=?",
                    (reason, _now_iso(), sid),
                )
                conn.commit()
        except Exception:
            pass
    _clear_file(root)
    try:
        from app.local_login_gate import set_last_desktop_login

        set_last_desktop_login(None)
    except Exception:
        pass


def get_active_desktop_session(base: Path | None = None, *, touch: bool = True) -> dict[str, Any] | None:
    """Return session payload if still active within idle window."""
    root = _base_dir(base)
    data = _load_file(root)
    if not data or not data.get("sid"):
        return None
    idle = int(data.get("idle_minutes") or IDLE_MINUTES)
    last = float(data.get("last_activity") or 0)
    if time.time() - last > idle * 60:
        revoke_desktop_session(root, f"Inactive for {idle} minutes")
        return None
    sid = str(data["sid"])
    try:
        with _connect(root) as conn:
            row = conn.execute(
                "SELECT active, revoked FROM online_sessions WHERE session_id=?",
                (sid,),
            ).fetchone()
            if not row or not row["active"] or row["revoked"]:
                revoke_desktop_session(root, "Session revoked or expired in database")
                return None
            user = conn.execute(
                "SELECT * FROM users WHERE id=? AND active=1",
                (int(data["user_id"]),),
            ).fetchone()
            if not user:
                revoke_desktop_session(root, "User inactive")
                return None
    except Exception:
        return None
    if touch:
        touch_desktop_session(root)
    data["user"] = dict(user)
    try:
        from app.local_login_gate import set_last_desktop_login

        set_last_desktop_login(dict(user))
    except Exception:
        pass
    return data


def register_program_exit_handler(base: Path | None = None) -> None:
    root = _base_dir(base)

    def _on_exit() -> None:
        revoke_desktop_session(root, "Program closed")

    atexit.register(_on_exit)


def session_user_dict(base: Path | None = None, *, touch: bool = True) -> dict[str, Any] | None:
    sess = get_active_desktop_session(base, touch=touch)
    if not sess:
        return None
    return sess.get("user") or {
        "id": sess.get("user_id"),
        "username": sess.get("username"),
        "role": sess.get("role"),
    }
