# -*- coding: utf-8 -*-
"""Live chat sessions + admin broadcast channel for Shared Host / mobile."""
from __future__ import annotations

import html
import sqlite3
from datetime import datetime
from typing import Callable, Optional

from flask import abort, flash, jsonify, redirect, request, url_for

ADMIN_CHANNEL = "admin_broadcast"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_live_chat_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS live_chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            job_id INTEGER,
            channel_type TEXT DEFAULT 'team',
            created_by TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS live_chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            role TEXT,
            body TEXT NOT NULL,
            is_admin_broadcast INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES live_chat_sessions(id)
        );
        """
    )
    row = conn.execute(
        "SELECT id FROM live_chat_sessions WHERE channel_type=? LIMIT 1", (ADMIN_CHANNEL,)
    ).fetchone()
    if not row:
        ts = _now()
        conn.execute(
            """
            INSERT INTO live_chat_sessions (title, channel_type, created_by, active, created_at, updated_at)
            VALUES (?,?,?,?,?,?)
            """,
            ("J & R Office Announcements", ADMIN_CHANNEL, "system", 1, ts, ts),
        )
    conn.commit()


def register_live_chat_routes(
    app,
    *,
    db_fn: Callable,
    login_required: Callable,
    layout: Callable,
    current_user: Callable,
    is_admin_role: Callable,
    log_event: Callable,
    normalize_role: Callable,
    is_customer_or_external: Callable,
) -> None:
    """Register /chat routes on the Flask app."""

    def _role(user) -> str:
        return normalize_role(user.get("role", "") if user else "")

    def _can_use_team_chat(user) -> bool:
        role = _role(user)
        return role in {"admin", "manager", "worker", "helper", "viewer"}

    def _can_read_broadcast(user) -> bool:
        role = _role(user)
        return _can_use_team_chat(user) or is_customer_or_external(role)

    def _session_allowed(user, channel_type: Optional[str]) -> bool:
        if channel_type == ADMIN_CHANNEL:
            return _can_read_broadcast(user)
        return _can_use_team_chat(user)

    @app.route("/chat")
    @login_required("view_dashboard")
    def chat_home():
        conn = db_fn()
        ensure_live_chat_schema(conn)
        user = current_user()
        admin = is_admin_role(user.get("role", ""))
        role = _role(user)
        if is_customer_or_external(role):
            sessions = conn.execute(
                """
                SELECT s.id, s.title, s.channel_type, s.updated_at,
                       (SELECT COUNT(*) FROM live_chat_messages m WHERE m.session_id=s.id) AS msg_count
                FROM live_chat_sessions s WHERE s.active=1 AND s.channel_type=? ORDER BY s.updated_at DESC
                """,
                (ADMIN_CHANNEL,),
            ).fetchall()
        elif _can_use_team_chat(user):
            sessions = conn.execute(
                """
                SELECT s.id, s.title, s.channel_type, s.updated_at,
                       (SELECT COUNT(*) FROM live_chat_messages m WHERE m.session_id=s.id) AS msg_count
                FROM live_chat_sessions s WHERE s.active=1 ORDER BY s.updated_at DESC
                """
            ).fetchall()
        else:
            abort(403)
        rows = ""
        for s in sessions:
            label = html.escape(s["title"])
            if s["channel_type"] == ADMIN_CHANNEL:
                label = "Office Announcements (admin speak only)"
            rows += (
                f"<tr><td><a href='/chat/{s['id']}'>{label}</a></td>"
                f"<td>{html.escape(s['channel_type'] or '')}</td>"
                f"<td>{s['msg_count']}</td>"
                f"<td>{html.escape(s['updated_at'] or '')}</td></tr>"
            )
        admin_form = ""
        if admin:
            admin_form = """
            <div class='card'><h2>Post Office Announcement (admin only)</h2>
            <form method='post' action='/chat/admin/broadcast'>
            <p><textarea name='body' rows='3' placeholder='Message to all connected users' required></textarea></p>
            <button>Send Announcement</button></form></div>"""
        team_form = ""
        if admin or _role(user) == "manager":
            team_form = """
            <div class='card'><h2>New team chat</h2>
            <form method='post' action='/chat/create'>
            <p><input name='title' placeholder='Session title (e.g. JRC-403 field)' required style='width:100%;max-width:420px;padding:8px'></p>
            <button>Create team session</button></form></div>"""
        note = "Team threads for jobs and field work."
        if is_customer_or_external(role):
            note = "Customer/external view: Office Announcements only. Team chat and internal threads are hidden."
        body = admin_form + team_form + f"""
        <div class='card'><h2>Live Chat Sessions</h2>
        <p class='muted'>{note} Office Announcements channel is read-only for workers and customers — admin posts only.</p>
        <table><tr><th>Session</th><th>Type</th><th>Messages</th><th>Updated</th></tr>{rows}</table>
        <p><a class='btn btn2' href='/mobile'>Back to Mobile</a></p></div>"""
        return layout("Live Chat", body, "chat")

    @app.route("/chat/<int:session_id>", methods=["GET", "POST"])
    @login_required("view_dashboard")
    def chat_session(session_id: int):
        conn = db_fn()
        ensure_live_chat_schema(conn)
        user = current_user()
        admin = is_admin_role(user.get("role", ""))
        sess = conn.execute(
            "SELECT * FROM live_chat_sessions WHERE id=? AND active=1", (session_id,)
        ).fetchone()
        if not sess:
            return layout("Chat", "<div class='card'><p>Session not found.</p></div>", "chat")
        if not _session_allowed(user, sess["channel_type"]):
            abort(403)
        is_broadcast = sess["channel_type"] == ADMIN_CHANNEL
        if request.method == "POST":
            if is_broadcast and not admin:
                flash("Only admin can post to Office Announcements.", "error")
            elif is_customer_or_external(_role(user)):
                flash("Customer accounts cannot post to team chat.", "error")
            else:
                body = (request.form.get("body") or "").strip()
                if body:
                    conn.execute(
                        """
                        INSERT INTO live_chat_messages
                        (session_id, username, role, body, is_admin_broadcast, created_at)
                        VALUES (?,?,?,?,?,?)
                        """,
                        (
                            session_id,
                            user.get("username", ""),
                            user.get("role", ""),
                            body,
                            1 if is_broadcast else 0,
                            _now(),
                        ),
                    )
                    conn.execute(
                        "UPDATE live_chat_sessions SET updated_at=? WHERE id=?",
                        (_now(), session_id),
                    )
                    conn.commit()
                    log_event("Chat", f"Message in session {session_id}")
                    flash("Message sent.", "success")
            return redirect(url_for("chat_session", session_id=session_id))

        msgs = conn.execute(
            """
            SELECT username, role, body, created_at, is_admin_broadcast
            FROM live_chat_messages WHERE session_id=? ORDER BY id ASC LIMIT 200
            """,
            (session_id,),
        ).fetchall()
        msg_html = ""
        for m in msgs:
            who = html.escape(m["username"] or "")
            when = html.escape(m["created_at"] or "")
            text = html.escape(m["body"] or "").replace("\n", "<br>")
            badge = " <span class='pill'>ADMIN</span>" if m["is_admin_broadcast"] else ""
            msg_html += f"<div class='card' style='padding:12px;margin-bottom:8px'><b>{who}</b>{badge} <span class='muted'>{when}</span><p>{text}</p></div>"

        compose = ""
        if is_customer_or_external(_role(user)):
            compose = "<div class='card'><p class='muted'>Read-only channel for your account type.</p></div>"
        elif not is_broadcast or admin:
            compose = """
            <div class='card'><h3>Send message</h3>
            <form method='post'><p><textarea name='body' rows='3' required></textarea></p>
            <button>Send</button></form></div>"""
        elif is_broadcast:
            compose = "<div class='card'><p class='muted'>Office Announcements — read only. Admin posts updates here.</p></div>"

        title = html.escape(sess["title"] or "Chat")
        body = f"""
        <div class='card'><h2>{title}</h2>
        <p><a href='/chat'>All sessions</a> | <a href='/mobile'>Mobile</a></p></div>
        {msg_html or "<div class='card'><p>No messages yet.</p></div>"}
        {compose}"""
        return layout(title, body, "chat")

    @app.route("/chat/admin/broadcast", methods=["POST"])
    @login_required("view_dashboard")
    def chat_admin_broadcast():
        user = current_user()
        if not is_admin_role(user.get("role", "")):
            abort(403)
        conn = db_fn()
        ensure_live_chat_schema(conn)
        sess = conn.execute(
            "SELECT id FROM live_chat_sessions WHERE channel_type=? LIMIT 1", (ADMIN_CHANNEL,)
        ).fetchone()
        if not sess:
            abort(404)
        body = (request.form.get("body") or "").strip()
        if not body:
            flash("Message required.", "error")
            return redirect(url_for("chat_home"))
        sid = int(sess["id"])
        conn.execute(
            """
            INSERT INTO live_chat_messages
            (session_id, username, role, body, is_admin_broadcast, created_at)
            VALUES (?,?,?,?,1,?)
            """,
            (sid, user.get("username", ""), user.get("role", ""), body, _now()),
        )
        conn.execute("UPDATE live_chat_sessions SET updated_at=? WHERE id=?", (_now(), sid))
        conn.commit()
        log_event("Chat", "Admin broadcast posted")
        flash("Announcement sent to Office Announcements channel.", "success")
        return redirect(url_for("chat_session", session_id=sid))

    @app.route("/chat/create", methods=["POST"])
    @login_required("view_dashboard")
    def create_team_session():
        user = current_user()
        role = _role(user)
        if not (is_admin_role(user.get("role", "")) or role == "manager"):
            abort(403)
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("Session title required.", "error")
            return redirect(url_for("chat_home"))
        conn = db_fn()
        ensure_live_chat_schema(conn)
        ts = _now()
        cur = conn.execute(
            """
            INSERT INTO live_chat_sessions (title, channel_type, created_by, active, created_at, updated_at)
            VALUES (?,?,?,?,?,?)
            """,
            (title, "team", user.get("username", ""), 1, ts, ts),
        )
        conn.commit()
        sid = int(cur.lastrowid)
        log_event("Chat", f"Team session created: {title}")
        flash("Team chat session created.", "success")
        return redirect(url_for("chat_session", session_id=sid))

    @app.route("/api/chat/sessions")
    @login_required("view_dashboard")
    def api_chat_sessions():
        user = current_user()
        role = _role(user)
        conn = db_fn()
        ensure_live_chat_schema(conn)
        if is_customer_or_external(role):
            rows = conn.execute(
                "SELECT id, title, channel_type, updated_at FROM live_chat_sessions WHERE active=1 AND channel_type=? ORDER BY updated_at DESC",
                (ADMIN_CHANNEL,),
            ).fetchall()
        elif _can_use_team_chat(user):
            rows = conn.execute(
                "SELECT id, title, channel_type, updated_at FROM live_chat_sessions WHERE active=1 ORDER BY updated_at DESC"
            ).fetchall()
        else:
            abort(403)
        return jsonify([dict(r) for r in rows])

    @app.route("/api/chat/<int:session_id>/messages")
    @login_required("view_dashboard")
    def api_chat_messages(session_id: int):
        user = current_user()
        conn = db_fn()
        ensure_live_chat_schema(conn)
        sess = conn.execute(
            "SELECT channel_type FROM live_chat_sessions WHERE id=? AND active=1", (session_id,)
        ).fetchone()
        if not sess or not _session_allowed(user, sess["channel_type"]):
            abort(403)
        rows = conn.execute(
            """
            SELECT id, username, role, body, is_admin_broadcast, created_at
            FROM live_chat_messages WHERE session_id=? ORDER BY id DESC LIMIT 50
            """,
            (session_id,),
        ).fetchall()
        return jsonify([dict(r) for r in rows])
