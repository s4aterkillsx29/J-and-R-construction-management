from __future__ import annotations

import csv
import datetime as dt
import functools
import hashlib
import html
import io
import os
import secrets
import sqlite3
from pathlib import Path
from flask import Flask, Response, abort, flash, g, get_flashed_messages, jsonify, redirect, render_template_string, request, send_file, session, url_for

APP_NAME = "J and R Construction Manager"
APP_VERSION = "7.2.0 Localhost Live Foundation"
BUSINESS = "J & R Construction"
PHONE = "(910) 712-0936"
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("JRC_DATA_DIR", BASE_DIR / "data"))
EXPORT_DIR = Path(os.environ.get("JRC_EXPORT_DIR", BASE_DIR / "exports"))
UPLOAD_DIR = Path(os.environ.get("JRC_UPLOAD_DIR", BASE_DIR / "uploads"))
DB_PATH = Path(os.environ.get("JRC_DB_PATH", DATA_DIR / "jr_business.db"))
SECRET_PATH = DATA_DIR / "server_secret.key"
for folder in (DATA_DIR, EXPORT_DIR, UPLOAD_DIR):
    folder.mkdir(parents=True, exist_ok=True)

def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")

def money(value) -> str:
    try:
        return "${:,.2f}".format(float(value or 0))
    except Exception:
        return "$0.00"

def num(value) -> float:
    try:
        return float(str(value or "0").replace("$", "").replace(",", "").strip() or 0)
    except Exception:
        return 0.0

def esc(value) -> str:
    return html.escape(str(value or ""))

def get_secret() -> str:
    if SECRET_PATH.exists():
        value = SECRET_PATH.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(48)
    SECRET_PATH.write_text(value, encoding="utf-8")
    return value

def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 250000).hex()
    return salt, digest

def verify_password(password: str, salt: str, digest: str) -> bool:
    return secrets.compare_digest(hash_password(password, salt)[1], digest)

def direct_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    conn = direct_db()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE,display_name TEXT,role TEXT,salt TEXT,password_hash TEXT,active INTEGER DEFAULT 1,must_change_password INTEGER DEFAULT 0,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,phone TEXT DEFAULT '',email TEXT DEFAULT '',address TEXT DEFAULT '',notes TEXT DEFAULT '',created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY AUTOINCREMENT,job_name TEXT,customer_id INTEGER,address TEXT DEFAULT '',status TEXT DEFAULT 'Lead',scope TEXT DEFAULT '',notes TEXT DEFAULT '',price REAL DEFAULT 0,paid REAL DEFAULT 0,material_budget REAL DEFAULT 0,helper_budget REAL DEFAULT 0,owner_labor_hours REAL DEFAULT 0,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id INTEGER,expense_date TEXT,vendor TEXT DEFAULT '',category TEXT DEFAULT '',description TEXT DEFAULT '',amount REAL DEFAULT 0,created_at TEXT);
CREATE TABLE IF NOT EXISTS workers(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,phone TEXT DEFAULT '',email TEXT DEFAULT '',default_day_rate REAL DEFAULT 140,notes TEXT DEFAULT '',active INTEGER DEFAULT 1,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS worker_payments(id INTEGER PRIMARY KEY AUTOINCREMENT,worker_id INTEGER,job_id INTEGER,work_date TEXT,amount REAL DEFAULT 0,status TEXT DEFAULT 'Paid',notes TEXT DEFAULT '',created_at TEXT);
CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id INTEGER,doc_type TEXT,title TEXT,amount REAL DEFAULT 0,status TEXT DEFAULT 'Draft',body TEXT DEFAULT '',created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS file_index(id INTEGER PRIMARY KEY AUTOINCREMENT,file_name TEXT,file_path TEXT,category TEXT DEFAULT '',notes TEXT DEFAULT '',uploaded_at TEXT);
CREATE TABLE IF NOT EXISTS customer_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,phone TEXT,email TEXT,address TEXT,request_type TEXT,message TEXT,status TEXT DEFAULT 'New',created_at TEXT);
CREATE TABLE IF NOT EXISTS worker_applications(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,phone TEXT,email TEXT,experience TEXT,transportation TEXT,message TEXT,status TEXT DEFAULT 'New',created_at TEXT);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT,username TEXT,action TEXT,detail TEXT,ip_address TEXT);
""")
    if not conn.execute("SELECT id FROM users WHERE username='admin'").fetchone():
        salt, digest = hash_password("admin")
        conn.execute("INSERT INTO users(username,display_name,role,salt,password_hash,active,must_change_password,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", ("admin", "Jacob Cosentino", "admin", salt, digest, 1, 1, now(), now()))
    if conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0:
        conn.execute("INSERT INTO customers(name,address,notes,created_at,updated_at) VALUES(?,?,?,?,?)", ("Jackie / 403 East 2nd", "403 East 2nd", "Active approved job. Deposit received and cashed.", now(), now()))
        customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO jobs(job_name,customer_id,address,status,scope,notes,price,paid,material_budget,helper_budget,owner_labor_hours,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", ("403 East 2nd exterior/demo approved scope", customer_id, "403 East 2nd", "Active - Deposit Received", "Brush/tree/vine cleanup, rock bed touch-up, stringer blocking, lower ground-level deck removal, pump-house removal, pipe cap installs, and related exterior cleanup.", "Track $1,000 deposit as business income. Separate deck rebuild quote remains on record unless approved/combined.", 2000, 1000, 250, 280, 24, now(), now()))
    conn.commit()
    conn.close()

app = Flask(__name__)
app.secret_key = get_secret()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
init_db()

def db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = direct_db()
    return g.db

@app.teardown_appcontext
def close_db(exc=None):
    conn = g.pop("db", None)
    if conn:
        conn.close()

@app.before_request
def load_user():
    g.user = None
    uid = session.get("uid")
    if uid:
        g.user = db().execute("SELECT * FROM users WHERE id=? AND active=1", (uid,)).fetchone()

def current_user():
    return getattr(g, "user", None)

def can(permission: str) -> bool:
    user = current_user()
    if not user:
        return False
    return user["role"] == "admin" or permission in {"dashboard", "jobs", "files", "mobile"}

def audit(action: str, detail: str = "") -> None:
    try:
        username = current_user()["username"] if current_user() else "public"
        db().execute("INSERT INTO audit_log(created_at,username,action,detail,ip_address) VALUES(?,?,?,?,?)", (now(), username, action, detail, request.remote_addr or ""))
        db().commit()
    except Exception:
        pass

def login_required(permission: str | None = None):
    def decorator(func):
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            if not current_user():
                return redirect(url_for("login", next=request.path))
            if permission and not can(permission):
                abort(403)
            return func(*args, **kwargs)
        return wrapped
    return decorator

CSS = """
body{margin:0;background:#07111f;color:#e5eefb;font-family:Segoe UI,Arial,sans-serif}a{color:#7dd3fc;text-decoration:none}.top{background:#0b1628;border-bottom:1px solid #263855;padding:14px 18px;position:sticky;top:0}.brand{font-size:20px;font-weight:700}.brand span,.muted{color:#94a3b8;font-size:12px}.nav{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap}.nav a,.btn,button{border:1px solid #263855;border-radius:12px;padding:9px 12px;background:#152238;color:#e5eefb;font-weight:700;display:inline-block;margin:4px}.btn.primary,button{background:#22c55e;color:#03110a}.shell{max-width:1180px;margin:auto;padding:18px}.card{background:#152238;border:1px solid #263855;border-radius:18px;padding:18px;margin:0 0 14px}.hero{border-left:5px solid #22c55e}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}.stat{background:#0d1729;border:1px solid #263855;border-radius:16px;padding:15px}.stat b{display:block;font-size:24px;margin-top:5px}table{width:100%;border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid #263855;text-align:left;vertical-align:top}th{background:#0d1729;color:#bfdbfe}input,select,textarea{width:100%;padding:10px;border:1px solid #334155;border-radius:12px;background:#0b1628;color:#e5eefb}textarea{min-height:85px}.fg{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}.flash{background:#123253;border:1px solid #2563eb;border-radius:12px;padding:10px;margin-bottom:10px}@media(max-width:700px){.shell{padding:10px}.card{padding:13px}td:nth-child(n+3),th:nth-child(n+3){display:none}}
"""

def nav() -> str:
    if not current_user():
        return ""
    links = [("Dashboard", "dashboard"), ("Jobs", "jobs"), ("Customers", "customers"), ("Estimates/Invoices", "documents"), ("Expenses", "expenses"), ("Payroll", "payroll"), ("Files", "files"), ("Reports", "reports"), ("Mobile", "mobile"), ("Admin", "admin"), ("Logout", "logout")]
    return "".join(f"<a href='{url_for(endpoint)}'>{label}</a>" for label, endpoint in links)

def page(title: str, body: str) -> str:
    flashes = "".join(f"<div class='flash'>{esc(message)}</div>" for _, message in get_flashed_messages(with_categories=True))
    who = f"Signed in as {esc(current_user()['display_name'])} ({esc(current_user()['role'])})" if current_user() else "Localhost / live-ready server"
    return render_template_string(f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(title)}</title><style>{CSS}</style></head><body><div class='top'><div class='brand'>{BUSINESS}<span><br>{APP_NAME} - {APP_VERSION}<br>{who}</span></div><div class='nav'>{nav()}</div></div><main class='shell'>{flashes}{body}<p class='muted' style='text-align:center'>{BUSINESS} - {PHONE} - {now()}</p></main></body></html>")

def options(table: str, label: str = "name") -> str:
    try:
        rows = db().execute(f"SELECT id,{label} FROM {table} ORDER BY {label}").fetchall()
        return "".join(f"<option value='{row['id']}'>{esc(row[label])}</option>" for row in rows)
    except Exception:
        return ""

@app.route("/api/health")
def api_health():
    return jsonify(ok=True, app=APP_NAME, version=APP_VERSION, db=str(DB_PATH), port=int(os.environ.get("JRC_PORT", "8765")), time=now())

@app.route("/api/connection")
def api_connection():
    return jsonify(ok=True, message="J&R Construction Manager server is reachable.", login="/login", mobile="/mobile", health="/api/health")

@app.route("/mobile/ping")
def mobile_ping():
    return jsonify(ok=True, message="Mobile endpoint ready", time=now())

@app.route("/")
def home():
    return redirect(url_for("dashboard" if current_user() else "login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        row = db().execute("SELECT * FROM users WHERE username=? AND active=1", (request.form.get("username", "").strip(),)).fetchone()
        if row and verify_password(request.form.get("password", ""), row["salt"], row["password_hash"]):
            session.clear()
            session["uid"] = row["id"]
            session["role"] = row["role"]
            audit("login", "success")
            if row["must_change_password"]:
                flash("Default admin login works. Change the password in Admin before live use.", "warning")
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Login failed. First setup default is admin / admin.", "error")
        audit("login_failed", request.form.get("username", ""))
    return page("Login", "<div class='card hero'><h1>J & R Construction Manager Login</h1><p>Localhost is working when this page opens. First setup: <b>admin</b> / <b>admin</b>.</p></div><div class='card'><form method='post'><p><label>Username</label><input name='username' value='admin'></p><p><label>Password</label><input type='password' name='password' value='admin'></p><button>Login</button><a class='btn' href='/connect'>Connection Test</a></form></div>")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required("dashboard")
def dashboard():
    conn = db()
    vals = {
        "jobs": conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
        "active": conn.execute("SELECT COUNT(*) FROM jobs WHERE status NOT LIKE 'Closed%'").fetchone()[0],
        "price": conn.execute("SELECT COALESCE(SUM(price),0) FROM jobs").fetchone()[0],
        "paid": conn.execute("SELECT COALESCE(SUM(paid),0) FROM jobs").fetchone()[0],
        "expenses": conn.execute("SELECT COALESCE(SUM(amount),0) FROM expenses").fetchone()[0],
        "payroll": conn.execute("SELECT COALESCE(SUM(amount),0) FROM worker_payments").fetchone()[0],
    }
    rows = conn.execute("SELECT j.*,c.name customer FROM jobs j LEFT JOIN customers c ON c.id=j.customer_id ORDER BY j.updated_at DESC LIMIT 10").fetchall()
    job_rows = "".join(f"<tr><td><a href='/jobs/{r['id']}'>{esc(r['job_name'])}</a><br><span class='muted'>{esc(r['customer'])}</span></td><td>{esc(r['status'])}</td><td>{money(r['price'])}</td><td>{money(r['paid'])}</td></tr>" for r in rows)
    stats = "".join(f"<div class='stat'><span>{label}</span><b>{value}</b></div>" for label, value in [("Jobs", vals["jobs"]), ("Active", vals["active"]), ("Price", money(vals["price"])), ("Paid", money(vals["paid"])), ("Expenses", money(vals["expenses"])), ("Payroll", money(vals["payroll"]))])
    return page("Dashboard", f"<div class='card hero'><h1>Live Business Dashboard</h1><p>Login, dashboard, jobs, money, payroll, files, mobile, customer pages, and APIs are online.</p></div><div class='grid'>{stats}</div><div class='card'><h2>Recent Jobs</h2><table><tr><th>Job</th><th>Status</th><th>Price</th><th>Paid</th></tr>{job_rows}</table></div><div class='card'><a class='btn primary' href='/jobs/new'>New Job</a><a class='btn' href='/customers/new'>New Customer</a><a class='btn' href='/documents/new'>New Estimate/Invoice</a></div>")

@app.route("/customers")
@login_required("dashboard")
def customers():
    rows = db().execute("SELECT * FROM customers ORDER BY updated_at DESC").fetchall()
    table = "".join(f"<tr><td>{esc(r['name'])}</td><td>{esc(r['phone'])}</td><td>{esc(r['address'])}</td></tr>" for r in rows)
    return page("Customers", f"<div class='card'><h1>Customers</h1><a class='btn primary' href='/customers/new'>Add Customer</a></div><div class='card'><table><tr><th>Name</th><th>Phone</th><th>Address</th></tr>{table}</table></div>")

@app.route("/customers/new", methods=["GET", "POST"])
@login_required("dashboard")
def customer_new():
    if request.method == "POST":
        db().execute("INSERT INTO customers(name,phone,email,address,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (request.form["name"], request.form.get("phone", ""), request.form.get("email", ""), request.form.get("address", ""), request.form.get("notes", ""), now(), now()))
        db().commit()
        return redirect(url_for("customers"))
    return page("New Customer", "<div class='card'><h1>Add Customer</h1><form method='post'><div class='fg'><p><label>Name</label><input name='name' required></p><p><label>Phone</label><input name='phone'></p><p><label>Email</label><input name='email'></p><p><label>Address</label><input name='address'></p></div><p><label>Notes</label><textarea name='notes'></textarea></p><button>Save</button></form></div>")

@app.route("/jobs")
@login_required("jobs")
def jobs():
    rows = db().execute("SELECT j.*,c.name customer FROM jobs j LEFT JOIN customers c ON c.id=j.customer_id ORDER BY j.updated_at DESC").fetchall()
    table = "".join(f"<tr><td><a href='/jobs/{r['id']}'>{esc(r['job_name'])}</a><br><span class='muted'>{esc(r['customer'])} - {esc(r['address'])}</span></td><td>{esc(r['status'])}</td><td>{money(r['price'])}</td><td>{money(r['paid'])}</td><td>{money(num(r['price'])-num(r['paid']))}</td></tr>" for r in rows)
    return page("Jobs", f"<div class='card'><h1>Jobs</h1><a class='btn primary' href='/jobs/new'>New Job</a></div><div class='card'><table><tr><th>Job</th><th>Status</th><th>Price</th><th>Paid</th><th>Balance</th></tr>{table}</table></div>")

@app.route("/jobs/new", methods=["GET", "POST"])
@login_required("jobs")
def job_new():
    if request.method == "POST":
        db().execute("INSERT INTO jobs(job_name,customer_id,address,status,scope,notes,price,paid,material_budget,helper_budget,owner_labor_hours,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (request.form["job_name"], request.form.get("customer_id") or None, request.form.get("address", ""), request.form.get("status", "Lead"), request.form.get("scope", ""), request.form.get("notes", ""), num(request.form.get("price")), num(request.form.get("paid")), num(request.form.get("material_budget")), num(request.form.get("helper_budget")), num(request.form.get("owner_labor_hours")), now(), now()))
        db().commit()
        return redirect(url_for("jobs"))
    return page("New Job", f"<div class='card'><h1>New Job</h1><form method='post'><div class='fg'><p><label>Job Name</label><input name='job_name' required></p><p><label>Customer</label><select name='customer_id'><option value=''>None</option>{options('customers')}</select></p><p><label>Address</label><input name='address'></p><p><label>Status</label><input name='status' value='Lead'></p><p><label>Price</label><input name='price'></p><p><label>Paid/Deposit</label><input name='paid'></p><p><label>Material Budget</label><input name='material_budget'></p><p><label>Helper Budget</label><input name='helper_budget'></p><p><label>Owner Labor Hours</label><input name='owner_labor_hours'></p></div><p><label>Scope</label><textarea name='scope'></textarea></p><p><label>Notes</label><textarea name='notes'></textarea></p><button>Save Job</button></form></div>")

@app.route("/jobs/<int:job_id>")
@login_required("jobs")
def job_detail(job_id: int):
    row = db().execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        abort(404)
    return page("Job", f"<div class='card hero'><h1>{esc(row['job_name'])}</h1><p>{esc(row['status'])} - Balance {money(num(row['price'])-num(row['paid']))}</p></div><div class='card'><h2>Scope</h2><p>{esc(row['scope'])}</p><h2>Notes</h2><p>{esc(row['notes'])}</p></div>")

@app.route("/expenses", methods=["GET", "POST"])
@login_required("dashboard")
def expenses():
    if request.method == "POST":
        db().execute("INSERT INTO expenses(job_id,expense_date,vendor,category,description,amount,created_at) VALUES(?,?,?,?,?,?,?)", (request.form.get("job_id") or None, request.form.get("expense_date") or dt.date.today().isoformat(), request.form.get("vendor", ""), request.form.get("category", ""), request.form.get("description", ""), num(request.form.get("amount")), now()))
        db().commit()
        return redirect(url_for("expenses"))
    rows = db().execute("SELECT e.*,j.job_name FROM expenses e LEFT JOIN jobs j ON j.id=e.job_id ORDER BY e.id DESC").fetchall()
    table = "".join(f"<tr><td>{esc(r['expense_date'])}</td><td>{esc(r['job_name'])}</td><td>{esc(r['vendor'])}</td><td>{esc(r['description'])}</td><td>{money(r['amount'])}</td></tr>" for r in rows)
    return page("Expenses", f"<div class='card'><h1>Expenses</h1><form method='post'><div class='fg'><p><label>Job</label><select name='job_id'><option value=''>General</option>{options('jobs','job_name')}</select></p><p><label>Date</label><input type='date' name='expense_date' value='{dt.date.today().isoformat()}'></p><p><label>Vendor</label><input name='vendor'></p><p><label>Description</label><input name='description'></p><p><label>Amount</label><input name='amount'></p></div><button>Add Expense</button></form></div><div class='card'><table><tr><th>Date</th><th>Job</th><th>Vendor</th><th>Description</th><th>Amount</th></tr>{table}</table></div>")

@app.route("/payroll", methods=["GET", "POST"])
@login_required("dashboard")
def payroll():
    if request.method == "POST":
        if request.form.get("kind") == "worker":
            db().execute("INSERT INTO workers(name,phone,email,default_day_rate,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (request.form["name"], request.form.get("phone", ""), request.form.get("email", ""), num(request.form.get("default_day_rate") or 140), request.form.get("notes", ""), now(), now()))
        else:
            db().execute("INSERT INTO worker_payments(worker_id,job_id,work_date,amount,status,notes,created_at) VALUES(?,?,?,?,?,?,?)", (request.form.get("worker_id") or None, request.form.get("job_id") or None, request.form.get("work_date") or dt.date.today().isoformat(), num(request.form.get("amount")), request.form.get("status", "Paid"), request.form.get("notes", ""), now()))
        db().commit()
        return redirect(url_for("payroll"))
    workers = db().execute("SELECT * FROM workers ORDER BY name").fetchall()
    pays = db().execute("SELECT wp.*,w.name worker,j.job_name FROM worker_payments wp LEFT JOIN workers w ON w.id=wp.worker_id LEFT JOIN jobs j ON j.id=wp.job_id ORDER BY wp.id DESC").fetchall()
    wrows = "".join(f"<tr><td>{esc(w['name'])}</td><td>{money(w['default_day_rate'])}</td><td>{esc(w['notes'])}</td></tr>" for w in workers)
    prows = "".join(f"<tr><td>{esc(p['work_date'])}</td><td>{esc(p['worker'])}</td><td>{esc(p['job_name'])}</td><td>{money(p['amount'])}</td><td>{esc(p['status'])}</td></tr>" for p in pays)
    return page("Payroll", f"<div class='card hero'><h1>Payroll</h1></div><div class='grid'><div class='card'><h2>Add Worker</h2><form method='post'><input type='hidden' name='kind' value='worker'><p><label>Name</label><input name='name' required></p><p><label>Default Day Rate</label><input name='default_day_rate' value='140'></p><button>Save Worker</button></form></div><div class='card'><h2>Add Payment</h2><form method='post'><p><label>Worker</label><select name='worker_id'>{options('workers')}</select></p><p><label>Job</label><select name='job_id'><option value=''>General</option>{options('jobs','job_name')}</select></p><p><label>Amount</label><input name='amount' value='140'></p><button>Save Payment</button></form></div></div><div class='card'><h2>Workers</h2><table><tr><th>Name</th><th>Day Rate</th><th>Notes</th></tr>{wrows}</table></div><div class='card'><h2>Payments</h2><table><tr><th>Date</th><th>Worker</th><th>Job</th><th>Amount</th><th>Status</th></tr>{prows}</table></div>")

@app.route("/documents")
@login_required("jobs")
def documents():
    rows = db().execute("SELECT d.*,j.job_name FROM documents d LEFT JOIN jobs j ON j.id=d.job_id ORDER BY d.id DESC").fetchall()
    table = "".join(f"<tr><td>{esc(r['title'])}</td><td>{esc(r['doc_type'])}</td><td>{esc(r['job_name'])}</td><td>{money(r['amount'])}</td><td>{esc(r['status'])}</td></tr>" for r in rows)
    return page("Documents", f"<div class='card'><h1>Estimates / Invoices</h1><a class='btn primary' href='/documents/new'>New Document</a></div><div class='card'><table><tr><th>Title</th><th>Type</th><th>Job</th><th>Amount</th><th>Status</th></tr>{table}</table></div>")

@app.route("/documents/new", methods=["GET", "POST"])
@login_required("jobs")
def doc_new():
    if request.method == "POST":
        db().execute("INSERT INTO documents(job_id,doc_type,title,amount,status,body,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (request.form.get("job_id") or None, request.form.get("doc_type", "Estimate"), request.form["title"], num(request.form.get("amount")), request.form.get("status", "Draft"), request.form.get("body", ""), now(), now()))
        db().commit()
        return redirect(url_for("documents"))
    return page("New Document", f"<div class='card'><h1>New Estimate / Invoice</h1><form method='post'><div class='fg'><p><label>Job</label><select name='job_id'><option value=''>None</option>{options('jobs','job_name')}</select></p><p><label>Type</label><select name='doc_type'><option>Estimate</option><option>Invoice</option><option>Proposal</option></select></p><p><label>Title</label><input name='title' required></p><p><label>Amount</label><input name='amount'></p></div><p><label>Body</label><textarea name='body'>50% deposit due before work begins. Remaining balance due upon completion.</textarea></p><button>Save Document</button></form></div>")

@app.route("/files", methods=["GET", "POST"])
@login_required("files")
def files():
    if request.method == "POST":
        upload = request.files.get("file")
        if upload and upload.filename:
            safe = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in upload.filename)
            dest = UPLOAD_DIR / safe
            upload.save(dest)
            db().execute("INSERT INTO file_index(file_name,file_path,category,notes,uploaded_at) VALUES(?,?,?,?,?)", (dest.name, str(dest), request.form.get("category", ""), request.form.get("notes", ""), now()))
            db().commit()
        return redirect(url_for("files"))
    rows = db().execute("SELECT * FROM file_index ORDER BY id DESC").fetchall()
    table = "".join(f"<tr><td>{esc(r['file_name'])}</td><td>{esc(r['category'])}</td><td>{esc(r['notes'])}</td><td>{esc(r['uploaded_at'])}</td></tr>" for r in rows)
    return page("Files", f"<div class='card'><h1>Files</h1><form method='post' enctype='multipart/form-data'><p><input type='file' name='file'></p><p><label>Category</label><input name='category'></p><p><label>Notes</label><input name='notes'></p><button>Upload</button></form></div><div class='card'><table><tr><th>File</th><th>Category</th><th>Notes</th><th>Uploaded</th></tr>{table}</table></div>")

@app.route("/reports")
@login_required("dashboard")
def reports():
    return page("Reports", "<div class='card hero'><h1>Reports</h1><p>Export and review job data.</p><a class='btn primary' href='/api/export/jobs.csv'>Download Jobs CSV</a></div>")

@app.route("/admin", methods=["GET", "POST"])
@login_required("dashboard")
def admin():
    if current_user()["role"] != "admin":
        abort(403)
    if request.method == "POST":
        password = request.form.get("new_password", "")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        else:
            salt, digest = hash_password(password)
            db().execute("UPDATE users SET salt=?,password_hash=?,must_change_password=0,updated_at=? WHERE id=?", (salt, digest, now(), current_user()["id"]))
            db().commit()
            flash("Password changed.", "success")
    rows = db().execute("SELECT * FROM users ORDER BY id").fetchall()
    table = "".join(f"<tr><td>{esc(r['username'])}</td><td>{esc(r['display_name'])}</td><td>{esc(r['role'])}</td><td>{'Yes' if r['must_change_password'] else 'No'}</td></tr>" for r in rows)
    return page("Admin", f"<div class='card hero'><h1>Admin / Security</h1><p>Change default admin password before live use.</p><form method='post'><p><label>New Password</label><input type='password' name='new_password'></p><button>Change Password</button></form></div><div class='card'><table><tr><th>User</th><th>Name</th><th>Role</th><th>Must Change</th></tr>{table}</table></div>")

@app.route("/mobile/setup")
def mobile_setup_page():
    from app.mobile_phone_setup import render_mobile_setup_page

    port = int(os.environ.get("JRC_PORT", "8765"))
    user = current_user()
    body = render_mobile_setup_page(
        lan_ip="127.0.0.1",
        port=port,
        logged_in=bool(user),
        username=user["username"] if user else "",
        role=user["role"] if user else "",
        esc=esc,
    )
    return page("Phone Setup", f"<div class='card hero'><h1>Phone Setup</h1></div>{body}")

@app.route("/mobile")
@login_required("mobile")
def mobile():
    return page("Mobile", "<div class='card hero'><h1>Mobile Access</h1><p>Phone-friendly view for same Wi-Fi/VPN or secured cloud host.</p></div><div class='card'><a class='btn primary' href='/mobile/setup'>Phone Setup Guide</a><a class='btn' href='/dashboard'>Dashboard</a><a class='btn' href='/jobs'>Jobs</a><a class='btn' href='/files'>Files</a></div>")

@app.route("/connect")
def connect_page():
    return page("Connection OK", "<div class='card hero'><h1>Connection OK</h1><p>The J&R Construction Manager server answered correctly.</p><a class='btn primary' href='/mobile/setup'>Phone Setup Guide</a><a class='btn' href='/login'>Login</a><a class='btn' href='/api/health'>API Health</a></div>")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        db().execute("INSERT INTO customer_requests(name,phone,email,address,request_type,message,status,created_at) VALUES(?,?,?,?,?,?,?,?)", (request.form.get("name", ""), request.form.get("phone", ""), request.form.get("email", ""), request.form.get("address", ""), "Customer/Account Request", request.form.get("message", ""), "New", now()))
        db().commit()
        flash("Request sent.", "success")
    return page("Register", "<div class='card'><h1>Customer / Account Request</h1><form method='post'><p><label>Name</label><input name='name' required></p><p><label>Phone</label><input name='phone'></p><p><label>Message</label><textarea name='message'></textarea></p><button>Send Request</button></form></div>")

@app.route("/apply", methods=["GET", "POST"])
def apply():
    if request.method == "POST":
        db().execute("INSERT INTO worker_applications(name,phone,email,experience,transportation,message,status,created_at) VALUES(?,?,?,?,?,?,?,?)", (request.form.get("name", ""), request.form.get("phone", ""), request.form.get("email", ""), request.form.get("experience", ""), request.form.get("transportation", ""), request.form.get("message", ""), "New", now()))
        db().commit()
        flash("Application sent.", "success")
    return page("Apply", "<div class='card'><h1>Worker / Helper Application</h1><form method='post'><p><label>Name</label><input name='name' required></p><p><label>Phone</label><input name='phone'></p><p><label>Experience</label><textarea name='experience'></textarea></p><button>Send Application</button></form></div>")

@app.route("/api/jobs")
@login_required("jobs")
def api_jobs():
    rows = db().execute("SELECT id,job_name,address,status,price,paid,updated_at FROM jobs ORDER BY updated_at DESC").fetchall()
    return jsonify([dict(row) for row in rows])

@app.route("/api/export/jobs.csv")
@login_required("dashboard")
def jobs_csv():
    rows = db().execute("SELECT id,job_name,address,status,price,paid,created_at,updated_at FROM jobs ORDER BY id").fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "job_name", "address", "status", "price", "paid", "created_at", "updated_at"])
    for row in rows:
        writer.writerow([row[key] for key in row.keys()])
    return send_file(io.BytesIO(output.getvalue().encode("utf-8-sig")), mimetype="text/csv", as_attachment=True, download_name="jrc_jobs.csv")

@app.route("/static/manifest.json")
def manifest():
    return jsonify(name=APP_NAME, short_name="JRC Manager", start_url="/mobile", display="standalone")

@app.route("/static/service-worker.js")
def service_worker():
    return Response("self.addEventListener('install',e=>self.skipWaiting());", mimetype="application/javascript")

@app.errorhandler(403)
def forbidden(exc):
    return page("Permission Needed", "<div class='card'><h1>Permission Needed</h1><a class='btn' href='/dashboard'>Dashboard</a></div>"), 403

@app.errorhandler(404)
def not_found(exc):
    return page("Not Found", "<div class='card'><h1>Page Not Found</h1><a class='btn' href='/dashboard'>Dashboard</a></div>"), 404

def run() -> None:
    port = int(os.environ.get("JRC_PORT", "8765"))
    host = os.environ.get("JRC_HOST", "0.0.0.0")
    print(f"{APP_NAME} {APP_VERSION} starting on http://127.0.0.1:{port}", flush=True)
    print(f"Database: {DB_PATH}", flush=True)
    app.run(host=host, port=port, debug=False, threaded=True)

if __name__ == "__main__":
    run()
