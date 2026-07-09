"""One-time localhost SSO tokens — sync desktop login to browser session."""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("JRC_DB_PATH", str(BASE_DIR / "data" / "jr_business.db"))).expanduser()

TOKEN_TTL_SECONDS = 90


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    conn = conn or _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS desktop_sso_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            consumed INTEGER DEFAULT 0,
            consumed_at TEXT
        )
        """
    )
    conn.commit()
    if own:
        conn.close()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mint_desktop_sso_token(user_id: int, username: str) -> str:
    """Create a single-use token for /auth/desktop-bridge (localhost only)."""
    ensure_schema()
    token = secrets.token_urlsafe(32)
    now = time.time()
    expires = now + TOKEN_TTL_SECONDS
    with _connect() as conn:
        ensure_schema(conn)
        conn.execute(
            "DELETE FROM desktop_sso_tokens WHERE expires_at < ? OR consumed=1",
            (now - 3600,),
        )
        conn.execute(
            """INSERT INTO desktop_sso_tokens (token_hash, user_id, username, created_at, expires_at)
               VALUES (?,?,?,?,?)""",
            (_hash_token(token), int(user_id), username, now, expires),
        )
        conn.commit()
    return token


def consume_desktop_sso_token(token: str) -> dict | None:
    """Validate and consume token; return active user row dict or None."""
    if not token or len(token) < 16:
        return None
    ensure_schema()
    now = time.time()
    token_hash = _hash_token(token)
    with _connect() as conn:
        row = conn.execute(
            """SELECT * FROM desktop_sso_tokens
               WHERE token_hash=? AND consumed=0 AND expires_at > ?""",
            (token_hash, now),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE desktop_sso_tokens SET consumed=1, consumed_at=datetime('now','localtime') WHERE id=?",
            (row["id"],),
        )
        user = conn.execute(
            "SELECT * FROM users WHERE id=? AND active=1",
            (row["user_id"],),
        ).fetchone()
        conn.commit()
        return dict(user) if user else None
