# -*- coding: utf-8 -*-
"""Messenger Flask routes + poll API."""
from __future__ import annotations

import html
from typing import Callable

from flask import jsonify, request

from app.messenger import permissions, schema, service


def register_messenger_routes(
    app,
    *,
    db_fn: Callable,
    login_required: Callable,
    layout: Callable,
    current_user: Callable,
    normalize_role: Callable,
) -> None:
    @app.route("/api/messenger/sessions")
    @login_required()
    def api_messenger_sessions():
        user = current_user()
        role = normalize_role(user.get("role", ""))
        conn = db_fn()
        schema.ensure_messenger_schema(conn)
        sessions = service.list_sessions(conn, role)
        return jsonify({"ok": True, "sessions": sessions})

    @app.route("/api/messenger/poll")
    @login_required()
    def api_messenger_poll():
        user = current_user()
        role = normalize_role(user.get("role", ""))
        session_id = request.args.get("session_id", type=int)
        after_id = request.args.get("after_id", 0, type=int)
        if not session_id:
            return jsonify({"ok": False, "error": "session_id required"})
        conn = db_fn()
        ch_row = conn.execute(
            "SELECT channel_type FROM live_chat_sessions WHERE id=?", (session_id,)
        ).fetchone()
        if not ch_row or not permissions.can_read(role, ch_row["channel_type"]):
            return jsonify({"ok": False, "error": "Access denied"})
        return jsonify(service.poll_updates(conn, session_id, after_id))

    @app.route("/api/messenger/send", methods=["POST"])
    @login_required()
    def api_messenger_send():
        user = current_user()
        role = normalize_role(user.get("role", ""))
        session_id = request.form.get("session_id", type=int) or request.json.get("session_id") if request.is_json else None
        body = request.form.get("body") or (request.json or {}).get("body", "")
        conn = db_fn()
        ch_row = conn.execute(
            "SELECT channel_type FROM live_chat_sessions WHERE id=?", (session_id,)
        ).fetchone()
        channel = ch_row["channel_type"] if ch_row else "team"
        return jsonify(
            service.send_message(
                conn,
                session_id=session_id,
                username=user.get("username", ""),
                role=role,
                body=body,
                channel_type=channel,
            )
        )

    @app.route("/admin/command-center", methods=["GET"])
    @login_required("view_admin")
    def admin_command_center():
        from app.reliability import guardian_store

        conn = db_fn()
        guardian_store.ensure_schema(conn)
        g_status = guardian_store.latest_status(conn)
        pending = conn.execute(
            "SELECT COUNT(*) FROM office_ai_pending_actions WHERE status='Pending'"
        ).fetchone()[0]
        sessions = conn.execute(
            "SELECT username, ip_address, last_seen FROM online_sessions ORDER BY last_seen DESC LIMIT 15"
        ).fetchall()
        sess_rows = "".join(
            f"<tr><td>{html.escape(str(r['username']))}</td>"
            f"<td>{html.escape(str(r.get('ip_address','')))}</td>"
            f"<td>{html.escape(str(r.get('last_seen','')))}</td></tr>"
            for r in sessions
        )
        body = f"""
        <div class="card"><h2>Command Center</h2>
        <p>Guardian: <b>{html.escape(g_status)}</b> |
        Pending AI approvals: <b>{pending}</b></p>
        <p><a class="btn" href="/admin/live-sessions">Live Sessions</a>
        <a class="btn btn2" href="/admin/reliability">Guardian</a>
        <a class="btn btn2" href="/office-ai/approvals">Approvals</a>
        <a class="btn btn2" href="/chat">Messenger</a></p></div>
        <div class="card"><h2>Recent Sessions</h2>
        <table><tr><th>User</th><th>IP</th><th>Last seen</th></tr>{sess_rows or '<tr><td colspan=3>None</td></tr>'}</table></div>
        """
        return layout("Command Center", body, "admin")

    @app.route("/admin/live-sessions", methods=["GET"])
    @login_required("view_admin")
    def admin_live_sessions():
        conn = db_fn()
        rows = conn.execute(
            "SELECT * FROM online_sessions ORDER BY last_seen DESC LIMIT 50"
        ).fetchall()
        trs = "".join(
            f"<tr><td>{html.escape(str(r['username']))}</td>"
            f"<td>{html.escape(str(r.get('role','')))}</td>"
            f"<td>{html.escape(str(r.get('ip_address','')))}</td>"
            f"<td>{html.escape(str(r.get('user_agent','')))[:60]}</td>"
            f"<td>{html.escape(str(r.get('last_seen','')))}</td></tr>"
            for r in rows
        )
        body = f"""<div class="card"><h2>Live Sessions</h2>
        <p class="muted">Auto-refreshes every 10s</p>
        <table><tr><th>User</th><th>Role</th><th>IP</th><th>Device</th><th>Last seen</th></tr>
        {trs or '<tr><td colspan=5>No active sessions logged</td></tr>'}</table>
        <script src="/static/admin-live-sessions.js"></script></div>"""
        return layout("Live Sessions", body, "admin")
