# -*- coding: utf-8 -*-
"""Desktop session bridge for Open Office (jr_job_manager) + safe shutdown."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional


def _base_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def resume_user_from_desktop_session(db) -> Optional[dict]:
    """Return active user row if Start Center session is valid — skip second login."""
    try:
        from app.desktop_session import get_active_desktop_session

        sess = get_active_desktop_session(_base_dir(), touch=True)
        if not sess or not sess.get("user_id"):
            return None
        row = db.one("SELECT * FROM users WHERE id=? AND active=1", (int(sess["user_id"]),))
        if not row:
            return None
        user = dict(row)
        try:
            from app.local_login_gate import set_last_desktop_login

            set_last_desktop_login(user)
        except Exception:
            pass
        db.log("Session", f"Open Office resumed desktop session for {user.get('username', '')}.")
        return user
    except Exception:
        return None


def checkpoint_database(db) -> None:
    """Flush SQLite WAL before exit."""
    try:
        conn = getattr(db, "conn", None)
        if conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
    except Exception:
        pass


def safe_office_shutdown(app) -> None:
    """Save session, checkpoint DB, touch desktop session."""
    try:
        if hasattr(app, "current_user") and hasattr(app, "db"):
            tab = app.nb.tab(app.nb.select(), "text") if hasattr(app, "nb") else ""
            data = {
                "username": app.current_user.get("username", "") if app.current_user else "",
                "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "selected_tab": tab,
                "selected_job_id": getattr(app, "selected_job_id", None),
            }
            path = _base_dir() / "data" / "office_app_session.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass
    try:
        checkpoint_database(app.db)
    except Exception:
        pass
    try:
        from app.desktop_session import touch_desktop_session

        touch_desktop_session(_base_dir())
    except Exception:
        pass
    try:
        app.db.log("Session", "Open Office closed; data saved and checkpointed.")
    except Exception:
        pass


def sync_document_templates() -> Path:
    """Copy JRC templates into program document_templates for standards writing."""
    from app.document_standards_writer import ensure_document_templates

    return ensure_document_templates(_base_dir())
