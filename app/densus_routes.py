"""Densus JRC Admin Control Center — owner-approved admin access only.

Desktop Densus = security scans (owner PC).
Web hub = sessions, permissions, database tools.
Download/use requires owner approval for each admin (except primary owner).
"""
from __future__ import annotations

import html
import os
from functools import wraps
from pathlib import Path
from typing import Callable

from flask import abort, flash, redirect, request, send_file, session, url_for

from app.densus_access import (
    access_status,
    create_densus_download_zip,
    has_densus_access,
    is_primary_owner,
    list_grants,
    pending_count,
    record_download,
    resolve_densus_package_source,
    review_grant,
    submit_access_request,
)


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

    def _current_access() -> bool:
        conn = db()
        return has_densus_access(
            conn,
            session.get("user_id"),
            session.get("username", ""),
            session.get("role", ""),
        )

    def densus_access_required(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not _current_access():
                flash("Densus requires owner approval before download or use.", "error")
                return redirect(url_for("admin_densus"))
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

    def _access_gate_html(conn) -> str:
        username = session.get("username", "")
        st = access_status(conn, session.get("user_id"), username, session.get("role", ""))
        if st == "owner":
            pending = pending_count(conn)
            pending_block = ""
            if pending:
                pending_block = (
                    f"<p><span class='badge red'>{pending}</span> "
                    f"admin(s) waiting for Densus approval.</p>"
                )
            return (
                f"<div class='card'><h2>Densus access — Owner control</h2>"
                f"<p>You are the J&amp;R owner. Your account always has full Densus access.</p>"
                f"{pending_block}"
                f"<p class='muted'>Approve listed admins below before they can download or use Densus.</p></div>"
            )
        if st == "Approved":
            return (
                "<div class='card'><h2>Densus access</h2>"
                "<p><span class='badge ok'>Approved</span> "
                "The owner approved your Densus access. You may use the hub and download the package.</p></div>"
            )
        if st == "Pending":
            return (
                "<div class='card'><h2>Densus access — pending</h2>"
                "<p><span class='badge yellow'>Pending</span> "
                "Your request is waiting for the J&amp;R owner to approve Densus access.</p>"
                "<p class='muted'>You cannot download or run Densus tools until approved.</p></div>"
            )
        if st == "Denied":
            return (
                "<div class='card'><h2>Densus access — denied</h2>"
                "<p><span class='badge red'>Denied</span> "
                "The owner did not approve Densus access for this account.</p>"
                "<form method='post'><input type='hidden' name='action' value='request_access'>"
                "<p><label>Reason (optional)<br><textarea name='request_note' rows='2' "
                "style='width:100%'></textarea></label></p>"
                "<button type='submit'>Request again</button></form></div>"
            )
        if st == "Revoked":
            return (
                "<div class='card'><h2>Densus access — revoked</h2>"
                "<p><span class='badge red'>Revoked</span> "
                "Your Densus access was revoked by the owner.</p>"
                "<form method='post'><input type='hidden' name='action' value='request_access'>"
                "<button type='submit'>Request access again</button></form></div>"
            )
        return (
            "<div class='card'><h2>Densus access — owner approval required</h2>"
            "<p>Densus is restricted. The J&amp;R owner must approve each admin before download or use.</p>"
            "<form method='post'><input type='hidden' name='action' value='request_access'>"
            "<p><label>Why do you need Densus?<br><textarea name='request_note' rows='2' "
            "style='width:100%' placeholder='e.g. session monitoring on office PC'></textarea></label></p>"
            "<button type='submit' class='btn'>Request Densus access from owner</button></form></div>"
        )

    def _owner_approval_html(conn) -> str:
        if not is_primary_owner(session.get("username", "")):
            return ""
        pending = list_grants(conn, "Pending")
        approved = list_grants(conn, "Approved")
        rows = []
        for g in pending:
            gid = int(g["id"])
            note = html.escape(g.get("request_note") or "")
            rows.append(
                f"<tr><td><b>{html.escape(g.get('username') or '')}</b></td>"
                f"<td>{html.escape(g.get('requested_at') or '')}</td>"
                f"<td>{html.escape(g.get('request_ip') or '')}</td>"
                f"<td>{note}</td>"
                f"<td>"
                f"<form method='post' style='display:inline'>"
                f"<input type='hidden' name='action' value='approve_densus'>"
                f"<input type='hidden' name='grant_id' value='{gid}'>"
                f"<button type='submit'>Approve</button></form> "
                f"<form method='post' style='display:inline'>"
                f"<input type='hidden' name='action' value='deny_densus'>"
                f"<input type='hidden' name='grant_id' value='{gid}'>"
                f"<button type='submit' class='danger'>Deny</button></form>"
                f"</td></tr>"
            )
        pending_table = (
            "".join(rows)
            if rows
            else "<tr><td colspan='5'>No pending Densus access requests.</td></tr>"
        )
        approved_rows = []
        for g in approved:
            if is_primary_owner(g.get("username") or ""):
                continue
            gid = int(g["id"])
            approved_rows.append(
                f"<tr><td>{html.escape(g.get('username') or '')}</td>"
                f"<td>{html.escape(g.get('reviewed_at') or '')}</td>"
                f"<td>{html.escape(g.get('last_download_at') or 'Never')}</td>"
                f"<td><form method='post' style='display:inline'>"
                f"<input type='hidden' name='action' value='revoke_densus'>"
                f"<input type='hidden' name='grant_id' value='{gid}'>"
                f"<button type='submit' class='btn2 danger'>Revoke</button></form></td></tr>"
            )
        approved_table = (
            "".join(approved_rows)
            if approved_rows
            else "<tr><td colspan='4'>No other admins approved yet.</td></tr>"
        )
        return f"""
        <div class="card"><h2>Owner — approve Densus for listed admins</h2>
          <p class="muted">Only admins you approve may download or use Densus. Your owner account is always allowed.</p>
          <h3>Pending requests</h3>
          <table><tr><th>Admin</th><th>Requested</th><th>IP</th><th>Note</th><th>Action</th></tr>
          {pending_table}
          </table>
          <h3 style="margin-top:18px">Approved admins</h3>
          <table><tr><th>Admin</th><th>Approved</th><th>Last download</th><th>Action</th></tr>
          {approved_table}
          </table>
        </div>"""

    def _download_block_html(conn) -> str:
        if not _current_access():
            return ""
        pkg = resolve_densus_package_source()
        if pkg:
            return (
                f"<div class='card'><h3>Download Densus (approved admins only)</h3>"
                f"<p class='muted'>Source on this PC: <code>{html.escape(str(pkg))}</code></p>"
                f"<p><a class='btn' href='/admin/densus/download'>Download Densus install package (ZIP)</a></p>"
                f"<p class='muted'>After download: unzip, run <b>!!! START DENSUS INSTALL.vbs</b>, "
                f"then Install to Desktop. Desktop actions below require owner PC (localhost).</p></div>"
            )
        return (
            "<div class='card'><h3>Download Densus</h3>"
            "<p class='muted'>Install source not found on this server. "
            "Owner PC needs <code>Documents\\JRC\\Densus</code> before ZIP download works.</p></div>"
        )

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

        conn = db()
        densus_admin_dir(root)
        admin_user = session.get("username", "")
        allowed = _current_access()

        if request.method == "POST":
            action = request.form.get("action", "check")

            if action == "request_access":
                ok, msg = submit_access_request(
                    conn,
                    user_id=int(session.get("user_id") or 0),
                    username=admin_user,
                    note=request.form.get("request_note", ""),
                    request_ip=client_ip(),
                    now_iso=now_iso,
                )
                flash(msg, "success" if ok else "warning")
                append_session_log(root, "densus_access_request", admin_user, msg, admin_user)
                log_event("Densus", msg)
                return redirect(url_for("admin_densus"))

            if action in {"approve_densus", "deny_densus", "revoke_densus"}:
                decision = {"approve_densus": "Approved", "deny_densus": "Denied", "revoke_densus": "Revoked"}[action]
                gid = int(request.form.get("grant_id") or 0)
                ok, msg = review_grant(
                    conn,
                    gid,
                    decision=decision,
                    reviewer=admin_user,
                    notes=request.form.get("admin_notes", ""),
                    now_iso=now_iso,
                )
                flash(msg, "success" if ok else "error")
                append_session_log(root, f"densus_{decision.lower()}", str(gid), msg, admin_user)
                log_event("Densus", msg)
                return redirect(url_for("admin_densus"))

            if not allowed:
                flash("Owner must approve your Densus access first.", "error")
                return redirect(url_for("admin_densus"))

            check_html = ""
            suggested = ""
            scan_html = ""

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

        check_html = locals().get("check_html", "")
        suggested = locals().get("suggested", "")
        scan_html = locals().get("scan_html", "")

        install = resolve_densus_install()
        summary = fetch_user_summary(db)
        last = load_last_snapshot(root)
        admin_path = densus_admin_dir(root)

        install_note = (
            f"<p class='muted'>Desktop Densus: <code>{html.escape(str(install))}</code> "
            f"<span class='badge ok'>Installed</span></p>"
            if install
            else "<p class='muted'>Desktop Densus not installed — download package after owner approval.</p>"
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

        tools_block = ""
        if allowed:
            tools_block = f"""
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
        <div class="card"><h3>Role policy profiles (used when adding users)</h3><ul>{profiles}</ul></div>"""

        sessions_block = ""
        if allowed:
            sessions_block = f"""
        <div class="card"><h2>Active users / sessions</h2>
          <p class="muted">End a session or open the account to change role, password, or permission overrides.</p>
          <table><tr><th>User</th><th>Role</th><th>IP</th><th>Login</th><th>Last seen</th><th>Account</th><th>Action</th></tr>
          {_sessions_html()}
          </table>
          <form method="post" style="margin-top:10px">
            <input type="hidden" name="action" value="snapshot">
            <button type="submit" class="btn2">Save admin snapshot now</button>
          </form>
        </div>"""

        body = f"""
        <div class="card"><h2>Densus — JRC Manager Admin Control Center</h2>
          <p><b>Owner-approved admin tool.</b> Download and use require explicit owner approval for each admin account.</p>
          <p class="muted">Monitoring files: <code>{html.escape(str(admin_path))}</code> (not business Dropbox records)</p>
          {install_note}
          {last_note}
        </div>
        {_access_gate_html(conn)}
        {_owner_approval_html(conn)}
        {_download_block_html(conn)}
        {sessions_block if allowed else ""}
        {f'''<div class="grid">
          <div class="stat">Users<b>{summary.get('total_users', 0)}</b><span class="muted">Total accounts</span></div>
          <div class="stat">Active accounts<b>{summary.get('active_accounts', 0)}</b></div>
          <div class="stat">Online now<b>{summary.get('online_sessions', 0)}</b></div>
          <div class="stat">Pending logins<b>{summary.get('pending_requests', 0)}</b></div>
        </div>
        <div class="card"><h2>Quick admin links</h2>
          <p>
            <a class="btn" href="/admin/database/accounts">Account database hub</a>
            <a class="btn btn2" href="/admin/database">All database tables</a>
            <a class="btn btn2" href="/admin">Admin command center</a>
            <a class="btn btn2" href="/admin/troubleshooter">Troubleshooter</a>
            <a class="btn btn2" href="/customers/requests">Customer requests</a>
          </p>
        </div>''' if allowed else ""}
        {tools_block}
        <div class="card"><h3>About Densus</h3>
          <p>WiFi audit and Windows posture scans run in the separate Desktop app — not mixed with job records.</p>
          <p><a class="btn btn2" href="/admin/densus/install-help">Install help</a>
          <a class="btn btn2" href="/admin">Back to Admin</a></p>
        </div>"""
        return layout("Densus JRC Admin", body, "densus")

    @app.route("/admin/densus/download")
    @login_required("view_admin")
    @admin_role_only
    @densus_access_required
    def admin_densus_download():
        conn = db()
        zip_path, msg = create_densus_download_zip()
        if not zip_path:
            flash(msg, "error")
            return redirect(url_for("admin_densus"))
        uid = session.get("user_id")
        if uid:
            record_download(conn, int(uid), now_iso)
        append_session_log(
            root,
            "densus_download",
            session.get("username", ""),
            msg,
            session.get("username", ""),
        )
        log_event("Densus", f"Package download by {session.get('username')}: {msg}")
        try:
            return send_file(
                zip_path,
                as_attachment=True,
                download_name="Densus-Install-Package.zip",
                mimetype="application/zip",
            )
        finally:
            try:
                zip_path.unlink(missing_ok=True)
            except Exception:
                pass

    @app.route("/admin/densus/install-help")
    @login_required("view_admin")
    @admin_role_only
    @densus_access_required
    def admin_densus_install_help():
        body = """<div class="card"><h2>Install Densus on Desktop (security scans)</h2>
        <p><span class="badge ok">Owner approved</span> — you may install Densus on an authorized admin PC.</p>
        <p>Densus data stays in <code>Desktop\\Densus\\data</code> — separate from business Dropbox records.</p>
        <ol>
          <li>Download the ZIP from <a href="/admin/densus/download">Densus download</a> (or use <code>Documents\\JRC\\Densus</code> on owner PC)</li>
          <li>Extract and double-click <b>!!! START DENSUS INSTALL.vbs</b></li>
          <li>Click <b>Install to Desktop</b></li>
          <li>Return to <b>Densus JRC Admin</b> and run quick scan (owner PC / localhost only)</li>
        </ol>
        <p><a class="btn" href="/admin/densus">Back to JRC Admin Hub</a></p></div>"""
        return layout("Install Densus", body, "densus")
