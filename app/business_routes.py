"""Business management routes — customers, invoices, overview dashboard."""
from __future__ import annotations

import datetime as dt
import html
from functools import wraps
from typing import Callable

from flask import abort, flash, redirect, request, session, url_for


def register_business_routes(app, layout, login_required, log_event, db, money, now_iso, parse_float):
    from app.role_utils import is_manager_or_admin

    def admin_only(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not is_manager_or_admin(session.get("role")):
                abort(403)
            return fn(*args, **kwargs)
        return wrapper

    @app.route("/business")
    @login_required("view_dashboard")
    def business_overview():
        conn = db()
        job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('Active','Approved','Waiting Payment')").fetchone()[0]
        cust_count = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        inv_open = conn.execute("SELECT COUNT(*) FROM invoices WHERE status NOT IN ('Paid','Void')").fetchone()[0]
        rev = conn.execute("SELECT COALESCE(SUM(paid),0) FROM jobs").fetchone()[0]
        exp = conn.execute("SELECT COALESCE(SUM(amount),0) FROM expenses").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM account_requests WHERE status='Pending'").fetchone()[0]
        body = f"""
        <div class="card"><h2>Business Command Center</h2>
          <p class="muted">Jobs, customers, money, and operations at a glance.</p>
        </div>
        <div class="grid">
          <div class="stat">Jobs<span class="badge ok">{job_count}</span><span class="muted">{active} active pipeline</span></div>
          <div class="stat">Customers<span class="badge ok">{cust_count}</span><span class="muted"><a href="/customers">Manage</a></span></div>
          <div class="stat">Open Invoices<span class="badge yellow">{inv_open}</span><span class="muted"><a href="/invoices">View</a></span></div>
          <div class="stat">Job Revenue<span class="badge ok">{money(rev)}</span><span class="muted">Paid on jobs</span></div>
          <div class="stat">Expenses<span class="badge">{money(exp)}</span><span class="muted"><a href="/expenses">Details</a></span></div>
          <div class="stat">Pending Requests<span class="badge yellow">{pending}</span><span class="muted"><a href="/admin">Admin</a></span></div>
        </div>
        <div class="card"><h2>Quick links</h2>
          <p><a class="btn" href="/jobs">Jobs</a>
          <a class="btn btn2" href="/customers">Customers</a>
          <a class="btn btn2" href="/invoices">Invoices</a>
          <a class="btn btn2" href="/payroll">Payroll</a>
          <a class="btn btn2" href="/bookkeeping">Bookkeeping</a>
          <a class="btn btn2" href="/admin/database">Database Editor</a></p>
        </div>"""
        return layout("Business", body, "business")

    @app.route("/customers", methods=["GET", "POST"])
    @login_required("view_jobs")
    @admin_only
    def customers_page():
        conn = db()
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Customer name required.", "error")
            else:
                conn.execute(
                    "INSERT INTO customers (name,phone,email,address,notes,created_at) VALUES (?,?,?,?,?,?)",
                    (name, request.form.get("phone"), request.form.get("email"),
                     request.form.get("address"), request.form.get("notes"), now_iso()),
                )
                conn.commit()
                log_event("Customers", f"Added customer {name}")
                flash("Customer saved.", "success")
            return redirect(url_for("customers_page"))
        rows = conn.execute("SELECT * FROM customers ORDER BY name").fetchall()
        trs = "".join(
            f"<tr><td>{r['id']}</td><td><b>{html.escape(r['name'])}</b></td>"
            f"<td>{html.escape(r['phone'] or '')}<br><span class='muted'>{html.escape(r['email'] or '')}</span></td>"
            f"<td>{html.escape(r['address'] or '')}</td>"
            f"<td>{html.escape((r['notes'] or '')[:80])}</td>"
            f"<td><a href='/admin/database/customers/edit/{r['id']}'>Edit</a></td></tr>"
            for r in rows
        )
        body = f"""
        <div class="card"><h2>Add Customer</h2>
          <form method="post"><div class="row3">
            <p><label>Name</label><input name="name" required></p>
            <p><label>Phone</label><input name="phone"></p>
            <p><label>Email</label><input name="email"></p>
          </div><p><label>Address</label><input name="address"></p>
          <p><label>Notes</label><textarea name="notes"></textarea></p>
          <button>Add Customer</button></form>
        </div>
        <div class="card"><h2>Customers</h2>
          <table><tr><th>ID</th><th>Name</th><th>Contact</th><th>Address</th><th>Notes</th><th></th></tr>
          {trs or "<tr><td colspan='6'>No customers yet.</td></tr>"}</table>
        </div>"""
        return layout("Customers", body, "customers")

    @app.route("/invoices", methods=["GET", "POST"])
    @login_required("view_money")
    @admin_only
    def invoices_page():
        conn = db()
        if request.method == "POST":
            total = parse_float(request.form.get("total"))
            paid = parse_float(request.form.get("amount_paid"))
            conn.execute(
                """INSERT INTO invoices (job_id,invoice_number,invoice_type,status,issue_date,due_date,
                   subtotal,paid_amount,balance_due,notes,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    request.form.get("job_id") or None,
                    request.form.get("invoice_number"),
                    "Invoice",
                    request.form.get("status") or "Draft",
                    request.form.get("issue_date") or dt.date.today().isoformat(),
                    request.form.get("due_date"),
                    total,
                    paid,
                    max(0.0, total - paid),
                    request.form.get("notes"),
                    now_iso(), now_iso(),
                ),
            )
            conn.commit()
            log_event("Invoices", f"Created invoice {request.form.get('invoice_number')}")
            flash("Invoice saved.", "success")
            return redirect(url_for("invoices_page"))
        jobs = conn.execute("SELECT id, job_name FROM jobs ORDER BY job_name").fetchall()
        job_opts = '<option value="">—</option>' + "".join(f'<option value="{j["id"]}">{html.escape(j["job_name"])}</option>' for j in jobs)
        rows = conn.execute(
            """SELECT i.*, j.job_name FROM invoices i
               LEFT JOIN jobs j ON j.id=i.job_id
               ORDER BY i.issue_date DESC, i.id DESC LIMIT 200"""
        ).fetchall()
        trs = "".join(
            f"<tr><td>{html.escape(r['invoice_number'] or str(r['id']))}</td>"
            f"<td>{html.escape(r['job_name'] or '')}</td>"
            f"<td>{html.escape(r['status'] or '')}</td>"
            f"<td>{money(r['subtotal'])}</td><td>{money(r['paid_amount'])}</td><td>{money(r['balance_due'])}</td>"
            f"<td><a href='/admin/database/invoices/edit/{r['id']}'>Edit</a></td></tr>"
            for r in rows
        )
        body = f"""
        <div class="card"><h2>New Invoice</h2>
          <form method="post"><div class="row3">
            <p><label>Invoice #</label><input name="invoice_number"></p>
            <p><label>Status</label><select name="status"><option>Draft</option><option>Sent</option><option>Partial</option><option>Paid</option><option>Void</option></select></p>
            <p><label>Total / Subtotal</label><input name="total"></p>
          </div><div class="row3">
            <p><label>Job</label><select name="job_id">{job_opts}</select></p>
            <p><label>Amount paid</label><input name="amount_paid" value="0"></p>
            <p><label>Due date</label><input name="due_date" type="date"></p>
          </div><p><label>Notes</label><textarea name="notes"></textarea></p>
          <button>Save Invoice</button></form>
        </div>
        <div class="card"><h2>Invoices</h2>
          <table><tr><th>#</th><th>Job</th><th>Status</th><th>Subtotal</th><th>Paid</th><th>Balance</th><th></th></tr>
          {trs or "<tr><td colspan='7'>No invoices yet.</td></tr>"}</table>
        </div>"""
        return layout("Invoices", body, "invoices")
