"""Admin database browser/editor — admin role only, safe CRUD on business tables."""
from __future__ import annotations

import hashlib
import html
import re
import secrets
import sqlite3
from functools import wraps
from typing import Callable, List, Set, Tuple

from flask import abort, flash, redirect, request, session, url_for

from app.role_utils import ROLE_LABELS, is_admin_role, normalize_role, role_display

# Tables admins may browse/edit (sqlite internal tables excluded).
ALLOWED_TABLES: Set[str] = {
    "customers", "jobs", "expenses", "workers", "worker_payments", "owner_labor", "owner_draws",
    "invoices", "invoice_payments", "evidence", "business_log", "app_settings",
    "file_sources", "file_index", "source_summaries", "shared_files", "shared_jobs",
    "customer_job_requests", "customer_request_events", "customer_user_profiles",
    "bookkeeping_ledgers", "bookkeeping_rules", "bookkeeping_runs", "bookkeeping_alerts",
    "filekeeping_reviews", "payroll_periods", "job_cost_snapshots", "job_applications",
    "application_events", "users", "permissions_override", "account_requests",
    "account_request_settings", "known_devices", "security_events", "health_events",
    "troubleshooting_actions", "host_events", "data_refresh_runs", "data_conflicts",
    "change_queue", "debit_payment_requests", "business_funds_ledger", "admin_withdrawals",
    "online_sessions", "mobile_devices", "ai_sources", "cloud_profiles", "record_locks",
    "owner_recovery_events",
}

ACCOUNT_TABLES: Tuple[str, ...] = (
    "users",
    "account_requests",
    "online_sessions",
    "customer_user_profiles",
    "known_devices",
    "permissions_override",
    "owner_recovery_events",
    "security_events",
)

READ_ONLY_COLUMNS: Set[str] = {"password_hash", "salt", "device_fingerprint"}
PAGE_SIZE = 50


def _hash_password(password: str, salt: str | None = None) -> Tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 250000).hex()
    return salt, digest


def _admin_only(fn: Callable):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_admin_role(session.get("role")):
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


def _safe_table(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name or ""):
        abort(400)
    if name not in ALLOWED_TABLES:
        abort(404)
    return name


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]


def _primary_key(conn: sqlite3.Connection, table: str) -> str:
    for row in conn.execute(f"PRAGMA table_info({table})"):
        if row[5]:
            return row[1]
    cols = _table_columns(conn, table)
    return cols[0] if cols else "rowid"


def _row_count(conn: sqlite3.Connection, table: str, where: str = "", params: tuple = ()) -> int:
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    return int(conn.execute(sql, params).fetchone()[0])


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    ).fetchone()
    return bool(row)


def _col(row, name: str, default: str = "") -> str:
    try:
        val = row[name]
        return "" if val is None else str(val)
    except Exception:
        return default


def register_admin_db_routes(app, layout, login_required, log_event, db, now_iso=None):
    """Register /admin/database* routes."""
    _now = now_iso or (lambda: "")

    @app.route("/admin/database")
    @login_required("view_admin")
    @_admin_only
    def admin_database_home():
        conn = db()
        account_counts = []
        for name in ACCOUNT_TABLES:
            if _table_exists(conn, name):
                try:
                    account_counts.append((name, _row_count(conn, name)))
                except sqlite3.Error:
                    pass
        account_rows = "".join(
            f"<tr><td><b>{html.escape(t)}</b></td><td>{cnt}</td>"
            f"<td><a class='btn btn2' href='/admin/database/{html.escape(t)}'>Browse</a></td></tr>"
            for t, cnt in account_counts
        )
        tables = []
        for name in sorted(ALLOWED_TABLES):
            if not _table_exists(conn, name):
                continue
            try:
                tables.append((name, _row_count(conn, name)))
            except sqlite3.Error:
                continue
        rows = "".join(
            f"<tr><td><b>{html.escape(t)}</b></td><td>{cnt}</td>"
            f"<td><a class='btn btn2' href='/admin/database/{html.escape(t)}'>Browse</a></td></tr>"
            for t, cnt in tables
        )
        body = f"""
        <div class="card"><h2>Account Database Editor</h2>
          <p class="muted">Manage login accounts, roles, sessions, and account requests. Password hashes stay read-only — use Reset Password below.</p>
          <p>
            <a class="btn" href="/admin/database/accounts">Account tools hub</a>
            <a class="btn btn2" href="/admin/database/users">All users</a>
            <a class="btn btn2" href="/admin/database/users/new">Add user</a>
            <a class="btn btn2" href="/admin">Admin panel</a>
            <a class="btn btn2" href="/backup">Download backup ZIP</a>
          </p>
        </div>
        <div class="card"><h2>Account tables</h2>
          <table><tr><th>Table</th><th>Rows</th><th>Action</th></tr>
          {account_rows or "<tr><td colspan='3'>No account tables found yet.</td></tr>"}
          </table>
        </div>
        <div class="card"><h2>All business tables</h2>
          <p class="muted">Browse and edit SQLite records. Changes are logged to the business log.</p>
          <table><tr><th>Table</th><th>Rows</th><th>Action</th></tr>{rows}</table>
        </div>"""
        return layout("Database Editor", body, "admin")

    @app.route("/admin/database/accounts")
    @login_required("view_admin")
    @_admin_only
    def admin_database_accounts():
        conn = db()
        users_n = _row_count(conn, "users") if _table_exists(conn, "users") else 0
        active_n = 0
        pending_n = 0
        online_n = 0
        if _table_exists(conn, "users"):
            active_n = _row_count(conn, "users", "active=1")
        if _table_exists(conn, "account_requests"):
            pending_n = _row_count(conn, "account_requests", "status='Pending'")
        if _table_exists(conn, "online_sessions"):
            online_n = _row_count(conn, "online_sessions", "active=1 AND revoked=0")
        recent_users = []
        if _table_exists(conn, "users"):
            recent_users = conn.execute(
                "SELECT id, username, display_name, role, active, last_login FROM users ORDER BY id DESC LIMIT 12"
            ).fetchall()
        user_rows = "".join(
            f"<tr><td>{r['id']}</td><td><b>{html.escape(r['username'])}</b></td>"
            f"<td>{html.escape(r['display_name'] or '')}</td>"
            f"<td>{html.escape(role_display(r['role']))}</td>"
            f"<td>{'Yes' if r['active'] else 'No'}</td>"
            f"<td>{html.escape(r['last_login'] or '')}</td>"
            f"<td><a href='/admin/database/users/manage/{r['id']}'>Manage</a> · "
            f"<a href='/admin/database/users/edit/{r['id']}'>Raw edit</a></td></tr>"
            for r in recent_users
        )
        body = f"""
        <div class="card"><h2>Account Database Tools</h2>
          <p class="muted">Use this hub to edit the account database — users, roles, passwords, sessions, and signup requests.</p>
          <div class="stats">
            <div class="stat"><b>{users_n}</b><br>Total users</div>
            <div class="stat"><b>{active_n}</b><br>Active users</div>
            <div class="stat"><b>{pending_n}</b><br>Pending requests</div>
            <div class="stat"><b>{online_n}</b><br>Online sessions</div>
          </div>
          <p style="margin-top:14px">
            <a class="btn" href="/admin/database/users/new">Add user account</a>
            <a class="btn btn2" href="/admin/database/users">Browse all users</a>
            <a class="btn btn2" href="/admin/database/account_requests">Pending requests</a>
            <a class="btn btn2" href="/admin/database/online_sessions">Online sessions</a>
            <a class="btn btn2" href="/admin">Full admin panel</a>
            <a class="btn btn2" href="/admin/densus">Densus JRC Admin Hub</a>
            <a class="btn btn2" href="/admin/database">All tables</a>
          </p>
        </div>
        <div class="card"><h2>Recent users</h2>
          <table><tr><th>ID</th><th>Username</th><th>Name</th><th>Role</th><th>Active</th><th>Last login</th><th>Tools</th></tr>
          {user_rows or "<tr><td colspan='7'>No users yet.</td></tr>"}
          </table>
        </div>"""
        return layout("Account Database", body, "admin")

    @app.route("/admin/database/users")
    @login_required("view_admin")
    @_admin_only
    def admin_database_users_redirect():
        return redirect(url_for("admin_database_browse", table_name="users"))

    @app.route("/admin/database/users/new", methods=["GET", "POST"])
    @login_required("view_admin")
    @_admin_only
    def admin_database_user_new():
        conn = db()
        roles = [r for r in ROLE_LABELS if r != "admin"] + ["admin"]
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            role = normalize_role(request.form.get("role") or "worker")
            display_name = (request.form.get("display_name") or "").strip()
            if not username:
                flash("Username is required.", "error")
            elif conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
                flash("Username already exists.", "error")
            elif len(password) < 8:
                flash("Password must be at least 8 characters.", "error")
            else:
                from app.network_server import enforce_new_password_policy

                ok, msg = enforce_new_password_policy(password, role=role)
                if not ok:
                    flash(msg, "error")
                else:
                    salt, ph = _hash_password(password)
                    conn.execute(
                        """INSERT INTO users (username, display_name, role, salt, password_hash, active,
                           must_change_password, created_at, notes) VALUES (?,?,?,?,?,1,1,?,?)""",
                        (username, display_name or username, role, salt, ph, _now(), "Created in Account Database Editor"),
                    )
                    conn.commit()
                    uid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    log_event("Admin DB", f"Created user {username} role={role}")
                    flash(f"User {username} created.", "success")
                    return redirect(url_for("admin_database_user_manage", user_id=uid))
        role_opts = "".join(
            f"<option value='{html.escape(r)}'>{html.escape(role_display(r))}</option>" for r in roles
        )
        body = f"""
        <div class="card"><h2>Add user account</h2>
          <form method="post">
            <p><label>Username</label><input name="username" required></p>
            <p><label>Display name</label><input name="display_name"></p>
            <p><label>Role</label><select name="role">{role_opts}</select></p>
            <p><label>Password</label><input name="password" type="password" required placeholder="Min 8 chars, upper/lower/number"></p>
            <button type="submit">Create account</button>
          </form>
          <p><a class="btn btn2" href="/admin/database/accounts">Back to account tools</a></p>
        </div>"""
        return layout("Add User", body, "admin")

    @app.route("/admin/database/users/manage/<int:user_id>", methods=["GET", "POST"])
    @login_required("view_admin")
    @_admin_only
    def admin_database_user_manage(user_id: int):
        conn = db()
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            abort(404)
        if request.method == "POST":
            action = request.form.get("action", "save")
            if action == "reset_password":
                new_pw = request.form.get("new_password") or ""
                if len(new_pw) < 8:
                    flash("Password must be at least 8 characters.", "error")
                else:
                    from app.network_server import enforce_new_password_policy

                    ok, msg = enforce_new_password_policy(new_pw, role=user["role"])
                    if not ok:
                        flash(msg, "error")
                    else:
                        salt, ph = _hash_password(new_pw)
                        conn.execute(
                            "UPDATE users SET salt=?, password_hash=?, must_change_password=0 WHERE id=?",
                            (salt, ph, user_id),
                        )
                        conn.commit()
                        log_event("Admin DB", f"Reset password for user id={user_id} ({user['username']})")
                        flash("Password updated.", "success")
            elif action == "toggle_active":
                new_active = 0 if int(user["active"] or 0) else 1
                conn.execute("UPDATE users SET active=? WHERE id=?", (new_active, user_id))
                conn.commit()
                log_event("Admin DB", f"Set user {user['username']} active={new_active}")
                flash("Account active status updated.", "success")
            elif action == "add_override":
                perm = (request.form.get("permission") or "").strip()
                allowed = 1 if request.form.get("allowed") == "1" else 0
                if perm:
                    conn.execute(
                        "DELETE FROM permissions_override WHERE user_id=? AND permission=?",
                        (user_id, perm),
                    )
                    conn.execute(
                        "INSERT INTO permissions_override (user_id, permission, allowed) VALUES (?,?,?)",
                        (user_id, perm, allowed),
                    )
                    conn.commit()
                    log_event("Admin DB", f"Permission override {perm}={'grant' if allowed else 'deny'} for {user['username']}")
                    flash(f"Permission override saved: {perm}", "success")
            elif action == "delete_override":
                perm = (request.form.get("perm") or "").strip()
                if perm:
                    conn.execute(
                        "DELETE FROM permissions_override WHERE user_id=? AND permission=?",
                        (user_id, perm),
                    )
                    conn.commit()
                    log_event("Admin DB", f"Removed permission override {perm} for {user['username']}")
                    flash(f"Removed override: {perm}", "success")
            elif action == "save":
                role = normalize_role(request.form.get("role") or user["role"])
                conn.execute(
                    """UPDATE users SET display_name=?, role=?, active=?, email=?, phone=?, title=?, notes=?
                       WHERE id=?""",
                    (
                        request.form.get("display_name") or user["display_name"],
                        role,
                        1 if request.form.get("active") else 0,
                        request.form.get("email") or None,
                        request.form.get("phone") or None,
                        request.form.get("title") or None,
                        request.form.get("notes") or None,
                        user_id,
                    ),
                )
                conn.commit()
                log_event("Admin DB", f"Updated account {user['username']} role={role}")
                flash("Account saved.", "success")
            return redirect(url_for("admin_database_user_manage", user_id=user_id))
        overrides = conn.execute(
            "SELECT permission, allowed FROM permissions_override WHERE user_id=? ORDER BY permission",
            (user_id,),
        ).fetchall()
        override_rows = "".join(
            f"<tr><td>{html.escape(o['permission'])}</td>"
            f"<td>{'Grant' if o['allowed'] else 'Deny'}</td>"
            f"<td><form method='post' style='display:inline'>"
            f"<input type='hidden' name='action' value='delete_override'>"
            f"<input type='hidden' name='perm' value='{html.escape(o['permission'])}'>"
            f"<button type='submit' class='btn2'>Remove</button></form></td></tr>"
            for o in overrides
        )
        try:
            from app.network_server import PERMISSIONS

            all_perms = sorted({p for perms in PERMISSIONS.values() for p in perms})
        except Exception:
            all_perms = sorted({o["permission"] for o in overrides})
        perm_opts = "".join(f"<option value='{html.escape(p)}'>{html.escape(p)}</option>" for p in all_perms)
        role_opts = "".join(
            f"<option value='{html.escape(r)}' {'selected' if normalize_role(user['role']) == r else ''}>"
            f"{html.escape(role_display(r))}</option>"
            for r in ROLE_LABELS
        )
        body = f"""
        <div class="card"><h2>Manage account: {html.escape(user['username'])}</h2>
          <p class="muted">ID {user_id} · Role {html.escape(role_display(user['role']))} ·
          {'Active' if user['active'] else 'Inactive'} · Last login {html.escape(user['last_login'] or 'never')}</p>
          <form method="post">
            <input type="hidden" name="action" value="save">
            <p><label>Display name</label><input name="display_name" value="{html.escape(user['display_name'] or '')}"></p>
            <p><label>Role</label><select name="role">{role_opts}</select></p>
            <p><label>Active</label><input type="checkbox" name="active" {'checked' if user['active'] else ''}></p>
            <p><label>Email</label><input name="email" value="{html.escape(_col(user, 'email'))}"></p>
            <p><label>Phone</label><input name="phone" value="{html.escape(_col(user, 'phone'))}"></p>
            <p><label>Title</label><input name="title" value="{html.escape(_col(user, 'title'))}"></p>
            <p><label>Notes</label><input name="notes" value="{html.escape(_col(user, 'notes'))}"></p>
            <button type="submit">Save account</button>
          </form>
          <form method="post" style="margin-top:18px">
            <input type="hidden" name="action" value="reset_password">
            <p><label>Reset password</label><input name="new_password" type="password" placeholder="New password (min 8)"></p>
            <button type="submit">Reset password</button>
          </form>
          <form method="post" style="margin-top:12px">
            <input type="hidden" name="action" value="toggle_active">
            <button type="submit" class="btn2">{'Deactivate' if user['active'] else 'Activate'} account</button>
          </form>
        </div>
        <div class="card"><h2>Permission overrides</h2>
          <p class="muted">Grant or deny a specific permission on top of the user's role. Use sparingly — role change is usually enough.</p>
          <table><tr><th>Permission</th><th>Effect</th><th></th></tr>
          {override_rows or "<tr><td colspan='3'>No overrides — role defaults only.</td></tr>"}
          </table>
          <form method="post" style="margin-top:14px">
            <input type="hidden" name="action" value="add_override">
            <div class="row3">
              <p><label>Permission</label><select name="permission">{perm_opts}</select></p>
              <p><label>Effect</label><select name="allowed"><option value="1">Grant</option><option value="0">Deny</option></select></p>
              <p style="padding-top:22px"><button type="submit">Add override</button></p>
            </div>
          </form>
          <p style="margin-top:14px">
            <a class="btn btn2" href="/admin/database/users/edit/{user_id}">Raw row editor</a>
            <a class="btn btn2" href="/admin/user/{user_id}">Admin panel user editor</a>
            <a class="btn btn2" href="/admin/database/accounts">Account tools</a>
          </p>
        </div>"""
        return layout(f"Account: {user['username']}", body, "admin")

    @app.route("/admin/database/users/edit/<int:user_id>", methods=["GET", "POST"])
    @login_required("view_admin")
    @_admin_only
    def admin_database_user_edit_raw(user_id: int):
        return redirect(url_for("admin_database_edit", table_name="users", row_id=str(user_id)))

    @app.route("/admin/database/<table_name>")
    @login_required("view_admin")
    @_admin_only
    def admin_database_browse(table_name: str):
        table = _safe_table(table_name)
        conn = db()
        page = max(1, int(request.args.get("page", 1) or 1))
        offset = (page - 1) * PAGE_SIZE
        q = (request.args.get("q") or "").strip()
        cols = _table_columns(conn, table)
        pk = _primary_key(conn, table)
        where, params = "", ()
        if q:
            if table == "users":
                where = "username LIKE ? OR display_name LIKE ? OR COALESCE(email,'') LIKE ?"
                params = (f"%{q}%", f"%{q}%", f"%{q}%")
            elif table == "account_requests":
                where = "requested_username LIKE ? OR COALESCE(display_name,'') LIKE ? OR status LIKE ?"
                params = (f"%{q}%", f"%{q}%", f"%{q}%")
            else:
                first = cols[1] if len(cols) > 1 else cols[0]
                where = f"{first} LIKE ?"
                params = (f"%{q}%",)
        total = _row_count(conn, table, where, params) if where else _row_count(conn, table)
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        sql += f" ORDER BY {pk} DESC LIMIT ? OFFSET ?"
        rows = conn.execute(sql, params + (PAGE_SIZE, offset)).fetchall()
        th = "".join(f"<th>{html.escape(c)}</th>" for c in cols) + "<th>Edit</th>"
        trs = []
        for r in rows:
            tds = "".join(f"<td>{html.escape(str(r[c])[:120])}</td>" for c in cols)
            rid = html.escape(str(r[pk]))
            if table == "users":
                edit = f"<a href='/admin/database/users/manage/{rid}'>Manage</a> · <a href='/admin/database/{html.escape(table)}/edit/{rid}'>Raw</a>"
            else:
                edit = f"<a href='/admin/database/{html.escape(table)}/edit/{rid}'>Edit</a>"
            tds += f"<td>{edit}</td>"
            trs.append(f"<tr>{tds}</tr>")
        nav = ""
        if page > 1:
            nav += f"<a class='btn btn2' href='?page={page-1}&q={html.escape(q)}'>Prev</a> "
        if offset + PAGE_SIZE < total:
            nav += f"<a class='btn btn2' href='?page={page+1}&q={html.escape(q)}'>Next</a>"
        extra = ""
        if table == "users":
            extra = "<a class='btn' href='/admin/database/users/new'>Add user</a> "
        if table in ACCOUNT_TABLES:
            extra += "<a class='btn btn2' href='/admin/database/accounts'>Account tools</a> "
        body = f"""
        <div class="card"><h2>{html.escape(table)}</h2>
          <p class="muted">{total} row(s) — page {page}</p>
          <form method="get" class="row"><input name="q" value="{html.escape(q)}" placeholder="Search...">
          <button type="submit">Search</button></form>
          <p>{extra}<a class='btn btn2' href='/admin/database'>All tables</a>
          <a class='btn' href='/admin/database/{html.escape(table)}/new'>Add row</a> {nav}</p>
        </div>
        <div class="card"><table><tr>{th}</tr>{''.join(trs) or "<tr><td colspan='99'>Empty table</td></tr>"}</table></div>"""
        return layout(f"DB: {table}", body, "admin")

    @app.route("/admin/database/<table_name>/edit/<row_id>", methods=["GET", "POST"])
    @login_required("view_admin")
    @_admin_only
    def admin_database_edit(table_name: str, row_id: str):
        table = _safe_table(table_name)
        conn = db()
        cols = _table_columns(conn, table)
        pk = _primary_key(conn, table)
        row = conn.execute(f"SELECT * FROM {table} WHERE {pk}=?", (row_id,)).fetchone()
        if not row:
            abort(404)
        if request.method == "POST":
            if request.form.get("confirm_delete") == "yes":
                conn.execute(f"DELETE FROM {table} WHERE {pk}=?", (row_id,))
                conn.commit()
                log_event("Admin DB", f"Deleted {table} {pk}={row_id}")
                flash(f"Deleted row {row_id} from {table}.", "success")
                return redirect(url_for("admin_database_browse", table_name=table))
            updates = []
            values = []
            for c in cols:
                if c == pk or c in READ_ONLY_COLUMNS:
                    continue
                if c in request.form:
                    val = request.form.get(c) or None
                    if c == "role":
                        val = normalize_role(val)
                    updates.append(f"{c}=?")
                    values.append(val)
            if updates:
                values.append(row_id)
                conn.execute(f"UPDATE {table} SET {', '.join(updates)} WHERE {pk}=?", values)
                conn.commit()
                log_event("Admin DB", f"Updated {table} {pk}={row_id}")
                flash("Row saved.", "success")
            return redirect(url_for("admin_database_edit", table_name=table, row_id=row_id))
        fields = []
        for c in cols:
            val = html.escape(str(row[c] if row[c] is not None else ""))
            ro = c in READ_ONLY_COLUMNS or c == pk
            if ro:
                fields.append(f"<p><label>{html.escape(c)}</label><input value='{val}' readonly></p>")
            else:
                fields.append(f"<p><label>{html.escape(c)}</label><input name='{html.escape(c)}' value='{val}'></p>")
        back = f"/admin/database/{html.escape(table)}"
        if table == "users":
            back = f"/admin/database/users/manage/{row_id}"
        body = f"""
        <div class="card"><h2>Edit {html.escape(table)} #{html.escape(row_id)}</h2>
          <form method="post">{''.join(fields)}<button type="submit">Save</button></form>
          <form method="post" style="margin-top:16px" onsubmit="return confirm('Delete this row permanently?');">
            <input type="hidden" name="confirm_delete" value="yes">
            <button type="submit" class="danger">Delete row</button>
          </form>
          <p style="margin-top:12px"><a class="btn btn2" href="{back}">Back</a></p>
        </div>"""
        return layout(f"Edit {table}", body, "admin")

    @app.route("/admin/database/<table_name>/new", methods=["GET", "POST"])
    @login_required("view_admin")
    @_admin_only
    def admin_database_new(table_name: str):
        table = _safe_table(table_name)
        if table == "users":
            return redirect(url_for("admin_database_user_new"))
        conn = db()
        cols = _table_columns(conn, table)
        pk = _primary_key(conn, table)
        editable = [c for c in cols if c != pk or pk == "rowid"]
        if request.method == "POST":
            insert_cols = [c for c in editable if c in request.form and c != "id"]
            if not insert_cols:
                flash("No fields to insert.", "error")
            else:
                placeholders = ",".join("?" for _ in insert_cols)
                vals = []
                for c in insert_cols:
                    val = request.form.get(c) or None
                    if c == "role":
                        val = normalize_role(val)
                    vals.append(val)
                conn.execute(
                    f"INSERT INTO {table} ({','.join(insert_cols)}) VALUES ({placeholders})",
                    vals,
                )
                conn.commit()
                new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                log_event("Admin DB", f"Inserted into {table} id={new_id}")
                flash("Row added.", "success")
                return redirect(url_for("admin_database_edit", table_name=table, row_id=str(new_id)))
        fields = "".join(
            f"<p><label>{html.escape(c)}</label><input name='{html.escape(c)}'></p>"
            for c in editable
            if c not in READ_ONLY_COLUMNS
        )
        body = f"""
        <div class="card"><h2>Add row — {html.escape(table)}</h2>
          <form method="post">{fields}<button type="submit">Create</button></form>
          <p><a class="btn btn2" href="/admin/database/{html.escape(table)}">Cancel</a></p>
        </div>"""
        return layout(f"New {table}", body, "admin")
