"""Densus JRC Admin Control Center — admin role ONLY.

Densus desktop app = security scans on owner PC.
This page = live JRC Manager admin: users, sessions, permissions, database tools.
Monitoring snapshots save to data/densus_admin/ (separate from business records).
"""
from __future__ import annotations

import html
from functools import wraps
from pathlib import Path
from typing import Callable

from flask import abort, flash, redirect, request, session, url_for


def register_densus_routes(
    app,
    layout,
    login_required,
    log_event,
    client_ip,
    db,
    now_iso,
    install_dir: Path | None = None,
):
    """Register /admin/densus* routes on the Flask app."""
    from app.densus_jrc_admin import (
        append_session_log,
        densus_admin_dir,
        fetch_active_sessions,
        fetch_user_summary,
        load_last_snapshot,
        revoke_session,
        save_admin_snapshot,
    )

    root = install_dir or Path(app.root_path).parent

    def admin_role_only(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if session.get("role") != "admin":
                abort(403)
            return fn(*args, **kwargs)
        return wrapper

    def _sessions_html() -> str:
        rows = fetch_active_sessions(db)
        if not rows:
            return "<tr><td colspan='7'>No active sessions right now.</td></tr>"
        out = []
        for r in rows:
            sid = html.escape(r.get("session_id") or "")
            user = html.escape(r.get("username") or "")
            role = html.escape(r.get("role") or "")
            ip = html.escape(r.get("ip_address") or "")
            login = html.escape(r.get("login_time") or "")
            seen = html.escape(r.get("last_seen") or "")
            uid = r.get("user_id")
            manage = (
                f"<a href='/admin/database/users/manage/{uid}'>Account</a>"
                if uid
                else ""
            )
            end = (
                f"<form method='post' style='display:inline'>"
                f"<input type='hidden' name='action' value='revoke_session'>"
                f"<input type='hidden' name='session_id' value='{sid}'>"
                f"<button type='submit' class='btn2'>End session</button></form>"
            )
            out.append(
                f"<tr><td>{user}</td><td>{role}</td><td>{ip}</td><td>{login}</td>"
                f"<td>{seen}</td><td>{manage}</td><td>{end}</td></tr>"
            )
        return "".join(out)

    @app.route("/admin/densus", methods=["GET", "POST"])
    @login_required("view_admin")
    @admin_role_only
    def admin_densus():
        from app.densus_bridge import (
            densus_installed,
            launch_densus_desktop,
            resolve_densus_install,
            run_densus_quick_scan_local,
            run_densus_troubleshooter,
        )
        from app.densus_policy import (
            POLICY_PROFILES,
            format_results_html,
            multi_platform_check,
            suggest_strong_password,
        )

        densus_admin_dir(root)
        check_html = ""
        suggested = ""
        scan_html = ""

        if request.method == "POST":
            action = request.form.get("action", "check")
            admin_user = session.get("username", "")
            if action == "check":
                pw = request.form.get("password", "")
                if pw:
                    results = multi_platform_check(pw)
                    check_html = (
                        f"<div class='card'><h3>Password Check Results</h3>"
                        f"{format_results_html(pw, results)}</div>"
                    )
                    log_event("Densus", "Admin password policy check (fp only)")
            elif action == "suggest":
                suggested = suggest_strong_password(18)
                flash("Strong password generated below. Copy it now — it is not stored.", "success")
            elif action == "launch":
                if client_ip() not in ("127.0.0.1", "::1"):
                    flash("Desktop Densus can only be opened on the owner PC (localhost).", "error")
                else:
                    ok, msg = launch_densus_desktop()
                    flash(msg, "success" if ok else "warning")
                    append_session_log(root, "launch_densus", "desktop", msg, admin_user)
            elif action == "repair":
                if client_ip() not in ("127.0.0.1", "::1"):
                    flash("Densus repair runs on the owner PC only.", "error")
                else:
                    ok, msg = run_densus_troubleshooter()
                    flash(msg[:400], "success" if ok else "warning")
                    append_session_log(root, "densus_repair", "troubleshooter", msg[:500], admin_user)
            elif action == "quick_scan":
                if client_ip() not in ("127.0.0.1", "::1"):
                    flash("Quick scan runs on the owner PC only.", "error")
                else:
                    ok, msg = run_densus_quick_scan_local()
                    scan_html = (
                        f"<div class='card'><h3>Desktop Densus Quick Scan</h3>"
                        f"<pre style='white-space:pre-wrap'>{html.escape(msg)}</pre></div>"
                    )
                    save_admin_snapshot(
                        root,
                        label="quick_scan",
                        payload={"ok": ok, "output": msg[:8000]},
                        db_fn=db,
                    )
                    flash("Quick scan finished. Snapshot saved to data/densus_admin/.", "success" if ok else "warning")
            elif action == "snapshot":
                path = save_admin_snapshot(
                    root,
                    label="admin_hub",
                    payload={"trigger": "manual", "by": admin_user},
                    db_fn=db,
                )
                flash(f"Admin snapshot saved: {path.name}", "success")
            elif action == "revoke_session":
                sid = request.form.get("session_id", "")
                ok, msg = revoke_session(
                    db,
                    sid,
                    "Ended from Densus JRC Admin Hub",
                    admin_user,
                )
                append_session_log(root, "revoke_session", sid, msg, admin_user)
                flash(msg, "success" if ok else "error")
                log_event("Densus", msg)
                return redirect(url_for("admin_densus"))

        install = resolve_densus_install()
        summary = fetch_user_summary(db)
        last = load_last_snapshot(root)
        admin_path = densus_admin_dir(root)

        install_note = (
            f"<p class='muted'>Desktop Densus (security scans): <code>{html.escape(str(install))}</code></p>"
            if install
            else "<p class='muted'>Install Densus to <code>Desktop\\Densus</code> for WiFi/Windows scans. "
            "This page works without it for user/session/database admin.</p>"
        )

        suggest_block = ""
        if suggested:
            suggest_block = (
                f"<div class='card'><h3>Suggested Password</h3>"
                f"<p><input readonly value='{html.escape(suggested)}' onclick='this.select()' "
                f"style='font-family:monospace;width:100%'></p></div>"
            )

        last_note = ""
        if last:
            last_note = f"<p class='muted'>Last snapshot: {html.escape(last.get('saved_at', ''))} — {html.escape(last.get('label', ''))}</p>"

        profiles = "".join(
            f"<li><b>{html.escape(p.label)}</b> — min {p.min_length} — {html.escape(p.description)}</li>"
            for p in POLICY_PROFILES.values()
        )

        body = f"""
        <div class="card"><h2>Densus — JRC Manager Admin Control Center</h2>
          <p><b>Admin only.</b> Sole admin hub for J &amp; R Construction Manager: active users, sessions,
          account permissions, and database tools. Business job/income files stay in Dropbox — not here.</p>
          <p class="muted">Admin monitoring files: <code>{html.escape(str(admin_path))}</code></p>
          {install_note}
          {last_note}
        </div>
        <div class="grid">
          <div class="stat">Users<b>{summary.get('total_users', 0)}</b><span class="muted">Total accounts</span></div>
          <div class="stat">Active accounts<b>{summary.get('active_accounts', 0)}</b></div>
          <div class="stat">Online now<b>{summary.get('online_sessions', 0)}</b></div>
          <div class="stat">Pending requests<b>{summary.get('pending_requests', 0)}</b></div>
        </div>
        <div class="card"><h2>Quick admin links</h2>
          <p>
            <a class="btn" href="/admin/database/accounts">Account database hub</a>
            <a class="btn btn2" href="/admin/database">All database tables</a>
            <a class="btn btn2" href="/admin">Admin command center</a>
            <a class="btn btn2" href="/admin/troubleshooter">Troubleshooter</a>
            <a class="btn btn2" href="/customers/requests">Customer requests</a>
          </p>
          <form method="post" style="display:inline;margin-top:10px">
            <input type="hidden" name="action" value="snapshot">
            <button type="submit" class="btn2">Save admin snapshot now</button>
          </form>
        </div>
        <div class="card"><h2>Active users / sessions</h2>
          <p class="muted">End a session or open the account to change role, password, or permission overrides.</p>
          <table><tr><th>User</th><th>Role</th><th>IP</th><th>Login</th><th>Last seen</th><th>Account</th><th>Action</th></tr>
          {_sessions_html()}
          </table>
        </div>
        <div class="grid">
          <div class="card"><h3>Password check (Densus policy)</h3>
            <form method="post">
              <input type="hidden" name="action" value="check">
              <input type="password" name="password" autocomplete="new-password" placeholder="Test password">
              <p style="margin-top:10px"><button type="submit">Check</button></p>
            </form>
          </div>
          <div class="card"><h3>Generate strong password</h3>
            <form method="post"><input type="hidden" name="action" value="suggest">
            <button type="submit" class="btn2">Generate</button></form>
          </div>
          <div class="card"><h3>Desktop Densus scans</h3>
            <form method="post"><input type="hidden" name="action" value="quick_scan">
            <button type="submit">Run quick scan (owner PC)</button></form>
            <form method="post" style="margin-top:8px"><input type="hidden" name="action" value="launch">
            <button type="submit" class="btn2">Open full Densus app</button></form>
            <form method="post" style="margin-top:8px"><input type="hidden" name="action" value="repair">
            <button type="submit" class="btn2">Run Densus auto-repair</button></form>
          </div>
        </div>
        {suggest_block}
        {check_html}
        {scan_html}
        <div class="card"><h3>Role policy profiles (used when adding users)</h3><ul>{profiles}</ul></div>
        <div class="card"><h3>Install Desktop Densus</h3>
          <p>WiFi audit and Windows posture scans run in the separate Desktop app — not mixed with job records.</p>
          <p><a class="btn btn2" href="/admin/densus/install-help">Install help</a>
          <a class="btn btn2" href="/admin">Back to Admin</a></p>
        </div>"""
        return layout("Densus JRC Admin", body, "densus")

    @app.route("/admin/densus/install-help")
    @login_required("view_admin")
    @admin_role_only
    def admin_densus_install_help():
        body = """<div class="card"><h2>Install Densus on Desktop (security scans)</h2>
        <p>Densus is the owner-PC security companion for JRC Manager. Its data stays in <code>Desktop\\Densus\\data</code>
        — separate from business Dropbox records.</p>
        <ol>
          <li>Open <code>Documents\\JRC\\Densus</code></li>
          <li>Double-click <b>!!! START DENSUS INSTALL.vbs</b></li>
          <li>Click <b>Install to Desktop</b></li>
          <li>Return to <b>Densus JRC Admin</b> and run quick scan or open full app</li>
        </ol>
        <p><a class="btn" href="/admin/densus">Back to JRC Admin Hub</a></p></div>"""
        return layout("Install Densus", body, "densus")
