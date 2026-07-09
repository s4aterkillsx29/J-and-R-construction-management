# -*- coding: utf-8 -*-
"""Office AI Flask routes."""
from __future__ import annotations

import html
import json
from typing import Any, Callable

from flask import flash, jsonify, redirect, request, url_for, abort

from app.office_ai.access import is_office_ai_user, office_ai_access_message

from app.office_ai.approval_gate import approve_action, deny_action, list_pending
from app.office_ai.config import (
    PROVIDER_MODEL_DEFAULTS,
    get_setting,
    office_ai_config,
    set_provider_api_key,
    set_setting,
)
from app.office_ai.orchestrator import OfficeAIOrchestrator
from app.office_ai.provider_router import get_provider


def register_office_ai_routes(
    app,
    *,
    db_fn: Callable,
    login_required: Callable,
    layout: Callable,
    current_user: Callable,
    log_event: Callable,
    CHATGPT_IMPORTS_DIR,
) -> None:
    # Schema is created in network_server init_db(); do not call db_fn() here (no app context yet).

    def _require_office_ai_admin():
        user = current_user()
        if not is_office_ai_user(user):
            abort(403, description=office_ai_access_message())

    @app.route("/office-ai", methods=["GET", "POST"])
    @login_required("configure_ai")
    def office_ai_chat():
        _require_office_ai_admin()
        user = current_user()
        conn = db_fn()
        orch = OfficeAIOrchestrator(conn)
        session_id = request.args.get("session_id", type=int)
        if request.method == "POST":
            sid_raw = request.form.get("session_id", "").strip()
            if sid_raw.isdigit():
                session_id = int(sid_raw)
            elif not sid_raw:
                session_id = None
        reply = ""
        if request.method == "POST":
            msg = (request.form.get("message") or "").strip()
            if msg:
                try:
                    result = orch.chat(
                        user_id=int(user["id"]),
                        username=user["username"],
                        message=msg,
                        session_id=session_id,
                    )
                except Exception as exc:
                    flash(f"Office AI error: {exc}", "error")
                    result = {"ok": False}
                if result.get("ok"):
                    reply = result.get("reply", "")
                    session_id = result.get("session_id")
                    if result.get("pending_approvals"):
                        flash(
                            f"{len(result['pending_approvals'])} action(s) waiting for approval.",
                            "warning",
                        )
                else:
                    flash(result.get("error", "Office AI error"), "error")

        cfg = office_ai_config(conn)
        pending_n = len(list_pending(conn))
        sessions = conn.execute(
            "SELECT id, title, updated_at FROM office_ai_sessions WHERE user_id=? ORDER BY updated_at DESC LIMIT 10",
            (user["id"],),
        ).fetchall()

        session_opts = "".join(
            f"<option value='{s['id']}' {'selected' if session_id == s['id'] else ''}>"
            f"#{s['id']} {html.escape(s['title'] or 'Chat')} ({html.escape(s['updated_at'] or '')})</option>"
            for s in sessions
        )
        reply_html = f"<div class='card'><h3>Assistant</h3><pre style='white-space:pre-wrap'>{html.escape(reply)}</pre></div>" if reply else ""

        body = f"""
        <div class='card'><h2>Office AI</h2>
          <p class='muted'>In-app assistant — same Dropbox rules as Cursor. Simple logs auto-save; money CSV changes need approval.</p>
          <p><b>Provider:</b> {html.escape(cfg['default_provider'])} | <b>Model:</b> {html.escape(get_setting(conn, 'office_ai_model', 'gpt-4o'))}
          {' | <span class=\"badge\">OpenAI key set</span>' if cfg['openai_configured'] else ' | <span class=\"badge warn\">Mock mode — add API key at /ai</span>'}</p>
          <p><a class='btn btn2' href='/office-ai/approvals'>Pending approvals ({pending_n})</a>
             <a class='btn btn2' href='/ai'>AI Settings</a>
             <a class='btn btn2' href='/chat'>Live Chat (team)</a></p>
        </div>
        <div class='card card-wide'>
          <form method='post'>
            <p><label>Session</label><select name='session_id'>{session_opts}<option value=''>— New session —</option></select></p>
            <p><label>Message</label><textarea name='message' rows='4' placeholder='Example: What is open on Lily fence? Or: Log helper pay note for JRC-315...' required autofocus></textarea></p>
            <button>Send to Office AI</button>
          </form>
        </div>
        {reply_html}
        """
        return layout("Office AI", body, "office-ai")

    @app.route("/office-ai/approvals", methods=["GET", "POST"])
    @login_required("configure_ai")
    def office_ai_approvals():
        _require_office_ai_admin()
        user = current_user()
        conn = db_fn()
        if request.method == "POST":
            action = request.form.get("action")
            aid = int(request.form.get("action_id") or 0)
            if action == "approve" and aid:
                result = approve_action(conn, aid, user["username"])
                flash(result.get("message") or result.get("error", "Done"), "success" if result.get("ok") else "error")
                log_event("Office AI", f"Approved pending action #{aid} by {user['username']}")
            elif action == "deny" and aid:
                deny_action(conn, aid, user["username"], request.form.get("note", ""))
                flash(f"Denied action #{aid}", "warning")
                log_event("Office AI", f"Denied pending action #{aid} by {user['username']}")
            return redirect(url_for("office_ai_approvals"))

        rows = list_pending(conn)
        cards = ""
        for r in rows:
            cards += f"""
            <div class='card'>
              <h3>#{r['id']} — {html.escape(r['tool_name'] or '')}</h3>
              <p class='muted'>Requested by {html.escape(r['username'] or '')} at {html.escape(r['created_at'] or '')}</p>
              <pre style='white-space:pre-wrap;background:rgba(0,0,0,.3);padding:12px;border-radius:8px'>{html.escape(r['preview_text'] or '')}</pre>
              <form method='post' style='display:flex;gap:8px;flex-wrap:wrap;margin-top:8px'>
                <input type='hidden' name='action_id' value='{r['id']}'>
                <button name='action' value='approve'>Approve &amp; Run</button>
                <button class='btn warn' name='action' value='deny'>Deny</button>
                <input name='note' placeholder='Deny reason (optional)' style='flex:1;min-width:200px'>
              </form>
            </div>"""
        if not cards:
            cards = "<div class='card'><p class='muted'>No pending actions.</p></div>"

        body = f"""
        <div class='card'><h2>Office AI — Pending Approvals</h2>
          <p class='muted'>Money, tax, and payroll CSV writes require your approval before they run.</p>
          <p><a class='btn btn2' href='/office-ai'>Back to Office AI</a></p>
        </div>
        {cards}
        """
        return layout("Office AI Approvals", body, "office-ai")

    @app.route("/api/office-ai/chat", methods=["POST"])
    @login_required("configure_ai")
    def api_office_ai_chat():
        _require_office_ai_admin()
        user = current_user()
        data = request.get_json(silent=True) or {}
        msg = (data.get("message") or request.form.get("message") or "").strip()
        if not msg:
            return jsonify({"ok": False, "error": "message required"}), 400
        try:
            orch = OfficeAIOrchestrator(db_fn())
            result = orch.chat(
                user_id=int(user["id"]),
                username=user["username"],
                message=msg,
                session_id=data.get("session_id"),
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500
        status = 200 if result.get("ok") else 502
        return jsonify(result), status

    @app.route("/api/office-ai/approve/<int:action_id>", methods=["POST"])
    @login_required("configure_ai")
    def api_office_ai_approve(action_id: int):
        _require_office_ai_admin()
        user = current_user()
        data = request.get_json(silent=True) or {}
        if data.get("deny") or request.form.get("deny"):
            result = deny_action(db_fn(), action_id, user["username"], data.get("note", ""))
        else:
            result = approve_action(db_fn(), action_id, user["username"])
        return jsonify(result)

    @app.route("/ai", methods=["GET", "POST"])
    @login_required("configure_ai")
    def ai_settings():
        _require_office_ai_admin()
        conn = db_fn()
        if request.method == "POST":
            action = request.form.get("action", "save")
            if action == "save":
                provider = request.form.get("provider") or "groq"
                set_setting(conn, "office_ai_default_provider", provider)
                default_model = PROVIDER_MODEL_DEFAULTS.get(provider, "llama-3.3-70b-versatile")
                set_setting(conn, "office_ai_model", request.form.get("model") or default_model)
                set_setting(conn, "office_ai_enabled", "1" if request.form.get("enabled") == "on" else "0")
                set_setting(conn, "office_ai_use_fallback", "1" if request.form.get("use_fallback") == "on" else "0")
                set_setting(conn, "office_ai_fallback_chain", request.form.get("fallback_chain") or "groq,gemini,ollama,openai,mock")
                set_setting(conn, "office_ai_ollama_url", request.form.get("ollama_url") or "http://127.0.0.1:11434/v1")
                for pname in ("openai", "groq", "gemini", "anthropic"):
                    key = (request.form.get(f"{pname}_api_key") or "").strip()
                    if key:
                        set_provider_api_key(conn, pname, key)
                flash("Office AI settings saved.", "success")
            elif action == "test":
                from app.office_ai.provider_router import get_provider

                provider = get_provider(conn)
                ok, msg = provider.test_connection()
                flash(f"Connection: {msg}", "success" if ok else "error")
            elif action == "add_source":
                conn.execute(
                    """INSERT INTO ai_sources (label,source_type,folder_path,api_enabled,status,notes,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,datetime('now','localtime'),datetime('now','localtime'))""",
                    (
                        request.form.get("label"),
                        request.form.get("source_type"),
                        request.form.get("folder_path"),
                        1 if request.form.get("api_enabled") == "on" else 0,
                        request.form.get("status") or "Configured",
                        request.form.get("notes"),
                    ),
                )
                conn.commit()
                flash("AI source saved.", "success")
            return redirect(url_for("ai_settings"))

        cfg = office_ai_config(conn)
        prov = cfg["default_provider"]
        model_val = html.escape(get_setting(conn, "office_ai_model", PROVIDER_MODEL_DEFAULTS.get(prov, "llama-3.3-70b-versatile")))
        fallback_val = html.escape(cfg.get("fallback_chain", "groq,gemini,ollama,openai,mock"))
        ollama_url = html.escape(cfg.get("ollama_url", "http://127.0.0.1:11434/v1"))
        provider_opts = "".join(
            f"<option value='{p}' {'selected' if prov == p else ''}>{p.title()}</option>"
            for p in ("groq", "gemini", "ollama", "openai", "anthropic", "mock")
        )
        key_status = " | ".join(
            f"{k}: {'set' if cfg.get(f'{k}_configured') else 'not set'}"
            for k in ("groq", "gemini", "openai", "anthropic")
        )
        rows = conn.execute("SELECT * FROM ai_sources ORDER BY id DESC").fetchall()
        trs = "".join(
            f"<tr><td>{html.escape(r['label'] or '')}</td><td>{html.escape(r['source_type'] or '')}</td>"
            f"<td>{html.escape(r['folder_path'] or '')}</td><td>{'Yes' if r['api_enabled'] else 'No'}</td>"
            f"<td>{html.escape(r['status'] or '')}</td></tr>"
            for r in rows
        )
        body = f"""
        <div class='card'><h2>Office AI Settings</h2>
          <p class='muted'>Owner/admin only. Keys stay in local SQLite — never Dropbox. Default: Groq free tier (fast).</p>
          <p class='muted'>{html.escape(key_status)}</p>
          <p><a class='btn' href='/office-ai'>Open Office AI Chat</a>
             <a class='btn btn2' href='/office-ai/approvals'>Pending Approvals</a></p>
        </div>
        <div class='card'><h2>Provider</h2>
          <form method='post'>
            <input type='hidden' name='action' value='save'>
            <div class='row3'>
              <p><label>Default provider</label>
                <select name='provider'>{provider_opts}</select></p>
              <p><label>Model</label><input name='model' value='{model_val}'></p>
              <p><label><input type='checkbox' name='enabled' {'checked' if cfg['enabled'] else ''}> Office AI enabled</label></p>
            </div>
            <p><label><input type='checkbox' name='use_fallback' {'checked' if get_setting(conn,'office_ai_use_fallback','1')=='1' else ''}> Auto-fallback if provider fails</label></p>
            <p><label>Fallback chain (comma-separated)</label><input name='fallback_chain' value='{fallback_val}' style='width:100%'></p>
            <p><label>Ollama URL (local free)</label><input name='ollama_url' value='{ollama_url}' style='width:100%'></p>
            <div class='row3'>
              <p><label>Groq API key (free tier)</label><input name='groq_api_key' type='password' placeholder='{'Configured' if cfg.get('groq_configured') else 'gsk_...'}'></p>
              <p><label>Gemini API key (free tier)</label><input name='gemini_api_key' type='password' placeholder='{'Configured' if cfg.get('gemini_configured') else 'AI...'}'></p>
              <p><label>OpenAI API key</label><input name='openai_api_key' type='password' placeholder='{'Configured' if cfg.get('openai_configured') else 'sk-...'}'></p>
            </div>
            <p><label>Anthropic API key</label><input name='anthropic_api_key' type='password' placeholder='{'Configured' if cfg.get('anthropic_configured') else 'sk-ant-...'}'></p>
            <button type='submit' name='action' value='save'>Save Settings</button>
          </form>
          <form method='post' style='margin-top:8px'>
            <input type='hidden' name='action' value='test'>
            <button class='btn btn2'>Test Connection</button>
          </form>
        </div>
        <div class='card'><h2>Knowledge Sources</h2>
          <p class='muted'>Tiered sources load from .cursor/rules and dropbox-records. ChatGPT exports scan from chatgpt_imports/.</p>
          <form method='post'>
            <input type='hidden' name='action' value='add_source'>
            <div class='row3'>
              <p><label>Label</label><input name='label' value='ChatGPT Business Export'></p>
              <p><label>Type</label><select name='source_type'>
                <option>chatgpt-import-folder</option><option>openai-api</option><option>manual-export</option></select></p>
              <p><label>Folder</label><input name='folder_path' value='{html.escape(str(CHATGPT_IMPORTS_DIR))}'></p>
            </div>
            <button>Add Source</button>
          </form>
          <table style='margin-top:12px'><tr><th>Label</th><th>Type</th><th>Path</th><th>API</th><th>Status</th></tr>{trs}</table>
        </div>
        """
        return layout("Office AI Settings", body, "ai")

    # Replace legacy ai_sources endpoint name for url_for compatibility
    app.view_functions["ai_sources"] = ai_settings

    @app.route("/api/office-ai/mobile/status")
    @login_required("view_dashboard")
    def api_office_ai_mobile_status():
        """Phase 3 — mobile clients check whether Office AI is available (admin only)."""
        user = current_user()
        conn = db_fn()
        cfg = office_ai_config(conn)
        allowed = is_office_ai_user(user)
        return jsonify(
            {
                "office_ai_enabled": cfg["enabled"] and allowed,
                "admin_only": True,
                "chat_url": "/office-ai" if allowed else None,
                "provider": cfg["default_provider"] if allowed else None,
            }
        )
