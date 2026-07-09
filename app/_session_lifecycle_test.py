"""Quick session lifecycle test (no Tk)."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path

from app.desktop_session import (
    IDLE_MINUTES,
    create_desktop_session,
    get_active_desktop_session,
)


def main() -> int:
    base = Path(tempfile.mkdtemp())
    try:
        (base / "data").mkdir()
        db = base / "data" / "jr_business.db"
        c = sqlite3.connect(db)
        c.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, role TEXT, active INTEGER, "
            "salt TEXT, password_hash TEXT, last_login TEXT)"
        )
        c.execute("INSERT INTO users VALUES (1,'admin','admin',1,'','','')")
        c.execute(
            "CREATE TABLE online_sessions (session_id TEXT PRIMARY KEY, user_id INTEGER, username TEXT, "
            "role TEXT, ip_address TEXT, user_agent TEXT, trusted_device_id TEXT, login_time TEXT, "
            "last_seen TEXT, active INTEGER DEFAULT 1, revoked INTEGER DEFAULT 0, revoke_reason TEXT)"
        )
        c.commit()
        c.close()
        os.environ["JRC_DB_PATH"] = str(db)
        user = {"id": 1, "username": "admin", "role": "admin"}
        create_desktop_session(user, base)
        assert get_active_desktop_session(base, touch=False)
        p = base / "data" / "desktop_active_session.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["last_activity"] = time.time() - (IDLE_MINUTES * 60 + 5)
        p.write_text(json.dumps(d), encoding="utf-8")
        assert get_active_desktop_session(base, touch=False) is None
        print("session lifecycle OK")
        return 0
    finally:
        import shutil

        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
