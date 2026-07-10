# -*- coding: utf-8 -*-
"""Admin popup modals — quick user/session actions without leaving the page."""
from __future__ import annotations

import html
import sqlite3
from typing import Callable, Optional

from flask import abort, jsonify, request

ADMIN_BROADCAST_CHANNEL = "admin_broadcast"


def register_admin_popup_routes(
    app,
    *,
    db_fn: Callable,
    login_required: Callable,
    current_user: Callable,
    is_admin_role: Callable,
    layout: Callable,
    log_event: Callable,
    now_iso: Callable,
    normalize_role: Callable,
) -> None:
    """Register admin popup API + page hooks."""

    def _require_admin():
        user = current_user()
        if not is_admin_role(user.get("role", "")):
            abort(403)
        return user

    @app.route("/api/admin/user-popup/<int:user_id>")
    @login_required("view_admin")
    def api_admin_user_popup(user_id: int):
        _require_admin()
        conn = db_fn()
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "User not found"})
        online = conn.execute(
            "SELECT session_id, ip_address, last_seen, user_agent FROM online_sessions WHERE user_id=? ORDER BY last_seen DESC LIMIT 3",
            (user_id,),
        ).fetchall()
        return jsonify(
            {
                "ok": True,
                "user": {
                    "id": row["id"],
                    "username": row["username"],
                    "role": row["role"],
                    "active": row["active"],
                    "email": row["email"] or "",
                    "phone": row["phone"] or "",
                    "last_login": row["last_login"] or "",
                    "title": row["title"] or "",
                },
                "sessions": [dict(s) for s in online],
            }
        )

    @app.route("/api/admin/user-popup/<int:user_id>/action", methods=["POST"])
    @login_required("view_admin")
    def api_admin_user_popup_action(user_id: int):
        admin = _require_admin()
        payload = request.get_json(silent=True) or {}
        action = (payload.get("action") or "").strip().lower()
        conn = db_fn()
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "User not found"})

        if action == "set_role":
            new_role = normalize_role(payload.get("role") or "")
            if not new_role:
                return jsonify({"ok": False, "error": "Role required"})
            conn.execute(
                "UPDATE users SET role=? WHERE id=?",
                (new_role, user_id),
            )
            conn.commit()
            log_event("Admin", f"Popup: role {row['username']} → {new_role}")
            return jsonify({"ok": True, "message": f"Role set to {new_role}"})

        if action == "toggle_active":
            new_active = 0 if row["active"] else 1
            conn.execute("UPDATE users SET active=? WHERE id=?", (new_active, user_id))
            conn.commit()
            state = "activated" if new_active else "deactivated"
            log_event("Admin", f"Popup: {row['username']} {state}")
            return jsonify({"ok": True, "message": f"Account {state}"})

        if action == "end_sessions":
            ended = conn.execute(
                "DELETE FROM online_sessions WHERE user_id=?",
                (user_id,),
            ).rowcount
            conn.commit()
            log_event("Admin", f"Popup: ended {ended} session(s) for {row['username']}")
            return jsonify({"ok": True, "message": f"Ended {ended} session(s)"})

        if action == "broadcast":
            body = (payload.get("body") or "").strip()
            if not body:
                return jsonify({"ok": False, "error": "Message required"})
            from app.live_chat import ensure_live_chat_schema

            ensure_live_chat_schema(conn)
            sess = conn.execute(
                "SELECT id FROM live_chat_sessions WHERE channel_type=? LIMIT 1",
                (ADMIN_BROADCAST_CHANNEL,),
            ).fetchone()
            if not sess:
                return jsonify({"ok": False, "error": "Broadcast channel missing"})
            ts = now_iso()
            conn.execute(
                """
                INSERT INTO live_chat_messages
                (session_id, username, role, body, is_admin_broadcast, created_at)
                VALUES (?,?,?,?,1,?)
                """,
                (
                    sess["id"],
                    admin.get("username", ""),
                    admin.get("role", ""),
                    body,
                    ts,
                ),
            )
            conn.execute(
                "UPDATE live_chat_sessions SET updated_at=? WHERE id=?",
                (ts, sess["id"]),
            )
            conn.commit()
            log_event("Admin", f"Popup broadcast to all users")
            return jsonify({"ok": True, "message": "Announcement sent"})

        return jsonify({"ok": False, "error": f"Unknown action: {action}"})

    @app.route("/api/admin/online-users")
    @login_required("view_admin")
    def api_admin_online_users():
        _require_admin()
        conn = db_fn()
        rows = conn.execute(
            """
            SELECT o.session_id, o.username, o.role, o.ip_address, o.last_seen,
                   o.user_agent, u.id AS user_id
            FROM online_sessions o
            LEFT JOIN users u ON u.username = o.username
            ORDER BY o.last_seen DESC LIMIT 50
            """
        ).fetchall()
        return jsonify({"ok": True, "users": [dict(r) for r in rows]})

    @app.route("/admin/popup-demo")
    @login_required("view_admin")
    def admin_popup_demo():
        """Admin reference page for popup actions."""
        body = """
        <div class="card"><h2>Admin Popup Windows</h2>
        <p class="muted">On the <a href="/admin">Admin Hub</a>, click <b>Quick popup</b> on any user row
        or online session to open actions without leaving the page.</p>
        <ul>
          <li>Change role inline</li>
          <li>Activate / deactivate account</li>
          <li>End all sessions for a user</li>
          <li>Send Office Announcement broadcast</li>
        </ul>
        <p><a class="btn" href="/admin">Open Admin Hub</a>
        <a class="btn btn2" href="/admin/command-center">Command Center</a></p></div>
        """
        return layout("Admin Popups", body, "admin")
