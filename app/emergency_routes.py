"""Emergency mastery-key routes — remote-safe owner admin recovery."""
from __future__ import annotations

import html
import time
from typing import Callable

from flask import flash, redirect, request, session, url_for

from app.emergency_access import grant_emergency_admin_access, verify_mastery_key

_ATTEMPTS: dict = {}
_MAX_ATTEMPTS = 8
_WINDOW_SEC = 3600


def _mastery_rate_limited(ip: str) -> bool:
    now = time.time()
    bucket = [t for t in _ATTEMPTS.get(ip, []) if now - t < _WINDOW_SEC]
    _ATTEMPTS[ip] = bucket
    return len(bucket) >= _MAX_ATTEMPTS


def _record_mastery_attempt(ip: str) -> None:
    _ATTEMPTS.setdefault(ip, []).append(time.time())


def register_emergency_routes(
    app,
    db,
    layout,
    now_iso,
    client_ip: Callable[[], str],
    log_security_event: Callable[..., None],
    default_admin_username: str,
) -> None:
    @app.route("/emergency-access", methods=["GET", "POST"])
    def emergency_access():
        ip = client_ip()
        if request.method == "POST":
            action = request.form.get("action", "login")
            key = request.form.get("mastery_key", "").strip()
            if _mastery_rate_limited(ip):
                log_security_event("mastery_key_rate_limit", "admin", f"Too many mastery key attempts from {ip}", "ERROR")
                flash("Too many emergency access attempts. Wait and try again, or use owner recovery on the master PC.", "error")
                return redirect(url_for("emergency_access"))
            _record_mastery_attempt(ip)
            if not verify_mastery_key(key):
                log_security_event("mastery_key_failed", "admin", f"Invalid mastery key attempt from {ip}", "WARN")
                flash("Invalid mastery key.", "error")
                return redirect(url_for("emergency_access"))
            if action == "reset_first_setup":
                from app.first_setup_security import reset_owner_to_first_setup
                ok, msg = reset_owner_to_first_setup(db(), key, ip, request.headers.get("User-Agent", ""))
                log_security_event("mastery_first_setup_reset", default_admin_username, msg, "WARN")
                flash(msg, "success" if ok else "error")
                return redirect(url_for("login"))
            conn = db()
            ok, msg = grant_emergency_admin_access(conn, ip, request.headers.get("User-Agent", ""))
            if not ok:
                flash(msg, "error")
                return redirect(url_for("emergency_access"))
            admin = conn.execute("SELECT * FROM users WHERE username=? LIMIT 1", (default_admin_username,)).fetchone()
            if not admin:
                from app.first_setup_security import LEGACY_OWNER_USERNAMES
                for legacy in LEGACY_OWNER_USERNAMES:
                    admin = conn.execute("SELECT * FROM users WHERE username=? LIMIT 1", (legacy,)).fetchone()
                    if admin:
                        break
            if admin:
                import uuid
                from app.role_utils import normalize_role

                sid = str(uuid.uuid4())
                session.clear()
                session.permanent = True
                session["user_id"] = admin["id"]
                session["username"] = admin["username"]
                session["role"] = normalize_role(admin["role"])
                session["sid"] = sid
                session["emergency_mastery_login"] = 1
                conn.execute(
                    "UPDATE users SET last_login=?, last_ip_address=?, last_user_agent=? WHERE id=?",
                    (now_iso(), ip, request.headers.get("User-Agent", ""), admin["id"]),
                )
                conn.execute(
                    "INSERT INTO online_sessions (session_id,user_id,username,role,ip_address,user_agent,"
                    "trusted_device_id,client_device_fingerprint,client_device_label,device_trust_status,"
                    "login_time,last_seen,active) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)",
                    (
                        sid, admin["id"], admin["username"], normalize_role(admin["role"]), ip,
                        request.headers.get("User-Agent", ""), "", "", "Emergency mastery", "emergency",
                        now_iso(), now_iso(),
                    ),
                )
                conn.commit()
            log_security_event("mastery_key_success", "admin", f"Emergency admin access granted from {ip}", "WARN")
            flash("Emergency admin access granted. Change passwords and review security events.", "warning")
            return redirect(url_for("dashboard"))
        body = """
        <div class='card card-narrow'>
          <h2>Emergency Owner Access</h2>
          <p class='muted'>Use your owner mastery key if you are locked out from any location — local PC, phone, cloud, or worker install.
          Every use is logged. This unlocks admin and signs you in as admin.</p>
          <form method='post'>
            <p><label>Mastery key (owner emergency only)</label>
            <input name='mastery_key' type='password' autocomplete='off' required placeholder='Owner emergency key'></p>
            <button>Emergency Admin Access</button>
          </form>
          <form method='post' style='margin-top:16px'>
            <input type='hidden' name='action' value='reset_first_setup'>
            <p><label>Mastery key (reset owner to ivygrows first-setup)</label>
            <input name='mastery_key' type='password' autocomplete='off' required></p>
            <button class='btn2'>Reset Owner to First-Setup (ivygrows)</button>
          </form>
          <p><a class='btn btn2' href='/login'>Back to normal login</a></p>
          <p class='muted'>Trusted local PC? <a href='/owner-recovery'>Owner recovery on master PC</a> can reset the admin password.</p>
        </div>
        """
        return layout("Emergency Access", body, "")
