import csv
import datetime as dt
import os
import hashlib
import secrets
import uuid
import json
import shutil
import sqlite3
import sys
import textwrap
import zipfile
import smtplib
from email.mime.text import MIMEText
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    REPORTLAB_OK = True
except Exception:
    REPORTLAB_OK = False

APP_NAME = "J and R Construction Manager"
APP_VERSION = "7.1 Primary Live Reliable Business Edition"
BUSINESS_NAME = "J & R Construction"
PHONE = "(910) 712-0936"
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"
EVIDENCE_DIR = BASE_DIR / "evidence"
DB_PATH = DATA_DIR / "jr_business.db"
SETTINGS_PATH = DATA_DIR / "manager_settings.json"
DEVICE_ID_PATH = DATA_DIR / "trusted_device_id.txt"
LOG_MIRROR_FILENAME = "JRC_Business_Log_Latest.txt"
DROPBOX_LEGACY_SOURCE_CANDIDATES = [
    "Invoices2026 1.0",
    "J and R Construction",
    "JRC",
]
DROPBOX_ORGANIZATION_FOLDERS = [
    "00_INBOX_To_File",
    "01_Jobs/Active",
    "01_Jobs/Completed",
    "01_Jobs/Leads_Estimates",
    "02_Documents_Invoices_Estimates_Quotes",
    "03_Receipts_Materials/Needs_Review",
    "03_Receipts_Materials/Filed",
    "04_Photos_Evidence/Before",
    "04_Photos_Evidence/During",
    "04_Photos_Evidence/After",
    "05_Helper_Pay_Workers",
    "06_Bookkeeping_Taxes/Income",
    "06_Bookkeeping_Taxes/Expenses",
    "06_Bookkeeping_Taxes/Schedule_C",
    "07_Backups",
    "08_Admin_Standards",
    "09_Archive",
    "10_Logs",
    "11_Exports",
    "12_Imports_ChatGPT",
]
DEFAULT_DROPBOX_BUSINESS_ROOT = BASE_DIR / "dropbox_business"

try:
    from app.ui_theme import (
        BG as DARK_BG,
        PANEL as PANEL_BG,
        CARD as CARD_BG,
        TEXT,
        MUTED,
        ACCENT,
        INFO as ACCENT_2,
        WARN as WARNING,
        DANGER,
        ENTRY_BG,
        configure_ttk,
    )
    from app.runtime_utils import open_web_dashboard
except Exception:
    DARK_BG = "#0a0f1c"
    PANEL_BG = "#111827"
    CARD_BG = "#151c2e"
    ACCENT = "#34d399"
    ACCENT_2 = "#60a5fa"
    TEXT = "#f1f5f9"
    MUTED = "#94a3b8"
    DANGER = "#f87171"
    WARNING = "#fbbf24"
    ENTRY_BG = "#0f172a"
    configure_ttk = None
    open_web_dashboard = None

TAX_CATEGORIES = [
    "Materials & Supplies",
    "Worker/Helper Pay",
    "Vehicle/Truck",
    "Tools/Equipment",
    "Insurance/Admin",
    "Rentals",
    "Advertising",
    "Office/Software",
    "Other",
]
JOB_STATUSES = ["Lead", "Estimate Sent", "Approved", "Active", "Waiting Payment", "Closed Paid", "Closed Unpaid", "On Hold"]
PAYMENT_METHODS = ["Cash", "Check", "Cash App", "Card", "Bank Transfer", "Other"]
DOC_TYPES = ["Estimate", "Invoice"]

DEFAULT_PAYMENT_TERMS = "50% deposit due before work begins. Remaining 50% balance due upon completion."
UNKNOWN_PROTECTION = "Price may change if hidden damage, rot, structural issues, or additional required work is discovered after opening up the work area."


def now_stamp():
    return dt.datetime.now().strftime("%Y-%m-%d %I:%M %p")


def iso_now():
    return dt.datetime.now().isoformat(timespec="seconds")


def money(value):
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "$0.00"


def parse_money(value):
    if value is None or value == "":
        return 0.0
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except Exception:
        return 0.0

def get_device_id():
    DATA_DIR.mkdir(exist_ok=True)
    if DEVICE_ID_PATH.exists():
        value = DEVICE_ID_PATH.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = str(uuid.uuid4())
    DEVICE_ID_PATH.write_text(value, encoding="utf-8")
    return value


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 250000).hex()
    return salt, digest


def verify_password(password, salt, password_hash):
    _, digest = hash_password(password, salt)
    if secrets.compare_digest(digest, password_hash):
        return True
    legacy = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 200000).hex()
    return secrets.compare_digest(legacy, password_hash)


def safe_filename(name):
    cleaned = "".join(ch if ch.isalnum() or ch in " ._-()" else "_" for ch in str(name))
    return cleaned.strip() or "file"


def ensure_dropbox_organization(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for rel in DROPBOX_ORGANIZATION_FOLDERS:
        (root / rel).mkdir(parents=True, exist_ok=True)
    readme = root / "_JRC_DROPBOX_ORGANIZATION_README.txt"
    if not readme.exists():
        readme.write_text(
            "J & R Construction Dropbox organization\n\n"
            "This folder tree is safe to recreate. It only creates missing folders and does not delete, move, or overwrite job files.\n\n"
            "Active Dropbox standard: use this one selected Dropbox business folder as the single J&R root.\n"
            "Do not create separate Dropbox business roots or separate invoice roots.\n"
            "Legacy candidates are search/index-only if they already exist, not folders to recreate:\n"
            + "\n".join(f"- Dropbox/{rel}" for rel in DROPBOX_LEGACY_SOURCE_CANDIDATES)
            + "\n\nOrganization folders created inside this one selected Dropbox business folder:\n"
            + "\n".join(f"- {rel}" for rel in DROPBOX_ORGANIZATION_FOLDERS)
            + "\n\nWhen the owner says \"log\", the latest business log mirror should be refreshed and copied here when Dropbox is configured.\n",
            encoding="utf-8",
        )
    return root


def resolve_dropbox_business_root(db=None):
    if db is not None:
        configured = db.get_setting("dropbox_folder", "").strip()
        if configured:
            return Path(configured)
    env_root = os.environ.get("JRC_DROPBOX_FOLDER", "").strip()
    if env_root:
        return Path(env_root)
    return DEFAULT_DROPBOX_BUSINESS_ROOT


class Database:
    def __init__(self, path: Path):
        DATA_DIR.mkdir(exist_ok=True)
        EXPORT_DIR.mkdir(exist_ok=True)
        EVIDENCE_DIR.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.init_schema()
        self.seed_defaults()

    def init_schema(self):
        cur = self.conn.cursor()
        cur.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                address TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                job_name TEXT NOT NULL,
                job_address TEXT,
                status TEXT NOT NULL,
                scope TEXT,
                contract_price REAL DEFAULT 0,
                deposit_required REAL DEFAULT 0,
                deposit_paid REAL DEFAULT 0,
                balance_paid REAL DEFAULT 0,
                payment_method TEXT,
                start_date TEXT,
                completion_date TEXT,
                callback_flag INTEGER DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(id)
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                date TEXT NOT NULL,
                vendor TEXT,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                receipt_status TEXT,
                notes TEXT,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE IF NOT EXISTS workers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                phone TEXT,
                email TEXT,
                address TEXT,
                w9_status TEXT DEFAULT 'Needed',
                default_day_rate REAL DEFAULT 140,
                notes TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS worker_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                job_id INTEGER,
                date TEXT NOT NULL,
                work_description TEXT,
                amount REAL NOT NULL DEFAULT 0,
                payment_method TEXT,
                status TEXT DEFAULT 'Paid',
                notes TEXT,
                FOREIGN KEY(worker_id) REFERENCES workers(id),
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE IF NOT EXISTS owner_labor (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                date TEXT NOT NULL,
                hours REAL DEFAULT 0,
                rate REAL DEFAULT 30,
                description TEXT,
                notes TEXT,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE IF NOT EXISTS evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                date TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT,
                evidence_type TEXT,
                description TEXT,
                notes TEXT,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE IF NOT EXISTS business_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                category TEXT NOT NULL,
                entry TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                doc_type TEXT NOT NULL,
                doc_number TEXT,
                date TEXT NOT NULL,
                title TEXT,
                scope TEXT,
                price REAL DEFAULT 0,
                deposit REAL DEFAULT 0,
                balance REAL DEFAULT 0,
                terms TEXT,
                exclusions TEXT,
                file_path TEXT,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                full_name TEXT,
                role TEXT NOT NULL DEFAULT 'User',
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                must_change_password INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_login TEXT,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        self.conn.commit()

    def seed_defaults(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM workers")
        if cur.fetchone()[0] == 0:
            for name, notes in [
                ("Brandon Hager", "Known J&R helper. Brake job helper confirmed as Brandon Hager."),
                ("Jackie White", "Known J&R helper. Has own transportation."),
            ]:
                cur.execute(
                    "INSERT OR IGNORE INTO workers(name, default_day_rate, notes, created_at) VALUES(?,?,?,?)",
                    (name, 140.0, notes, iso_now()),
                )
        cur.execute("SELECT COUNT(*) FROM business_log")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO business_log(timestamp, category, entry) VALUES(?,?,?)",
                (now_stamp(), "System", "J and R Construction Manager database created."),
            )
        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            salt, pw_hash = hash_password("admin")
            cur.execute(
                "INSERT INTO users(username, full_name, role, salt, password_hash, active, must_change_password, created_at, notes) VALUES(?,?,?,?,?,?,?,?,?)",
                ("admin", "Jacob Cosentino", "Admin", salt, pw_hash, 1, 1, iso_now(), "Default owner/admin account. Change password after first install."),
            )
        device_id = get_device_id()
        cur.execute("INSERT OR IGNORE INTO app_settings(key, value) VALUES(?,?)", ("owner", "Jacob Cosentino"))
        cur.execute("INSERT OR IGNORE INTO app_settings(key, value) VALUES(?,?)", ("trusted_admin_device_id", device_id))
        cur.execute("INSERT OR IGNORE INTO app_settings(key, value) VALUES(?,?)", ("dropbox_folder", ""))
        self.conn.commit()

    def q(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()

    def one(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return cur.fetchone()

    def execute(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        self.conn.commit()
        return cur.lastrowid

    def log(self, category, entry):
        self.execute("INSERT INTO business_log(timestamp, category, entry) VALUES(?,?,?)", (now_stamp(), category, entry))
        self.mirror_business_log()

    def mirror_business_log(self):
        try:
            EXPORT_DIR.mkdir(exist_ok=True)
            rows = self.q("SELECT timestamp, category, entry FROM business_log ORDER BY id DESC LIMIT 250")
            lines = [
                "J and R Construction Manager business log mirror",
                f"Updated: {now_stamp()}",
                "",
            ]
            for row in reversed(rows):
                lines.append(f"[{row['timestamp']}] {row['category']}: {row['entry']}")
            mirror_path = EXPORT_DIR / LOG_MIRROR_FILENAME
            mirror_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            dropbox_folder = self.get_setting("dropbox_folder", "").strip()
            if dropbox_folder:
                dropbox_root = ensure_dropbox_organization(dropbox_folder)
                shutil.copy2(mirror_path, dropbox_root / "10_Logs" / LOG_MIRROR_FILENAME)
                shutil.copy2(mirror_path, dropbox_root / LOG_MIRROR_FILENAME)
        except Exception:
            pass

    def get_setting(self, key, default=""):
        row = self.one("SELECT value FROM app_settings WHERE key=?", (key,))
        return row["value"] if row else default

    def set_setting(self, key, value):
        self.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


class LoginDialog(tk.Toplevel):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.result = None
        self.title("J and R Construction Manager Login")
        self.configure(bg=DARK_BG)
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        box = ttk.Frame(self, style="Card.TFrame", padding=20)
        box.pack(fill="both", expand=True, padx=18, pady=18)
        ttk.Label(box, text="J and R Construction Manager", style="CardHeader.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0,8))
        ttk.Label(box, text="Owned and operated by Jacob Cosentino", background=CARD_BG, foreground=MUTED).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0,12))
        ttk.Label(box, text="Username", background=CARD_BG).grid(row=2, column=0, sticky="w", pady=4)
        self.username = ttk.Entry(box, width=28)
        self.username.grid(row=2, column=1, pady=4)
        ttk.Label(box, text="Password", background=CARD_BG).grid(row=3, column=0, sticky="w", pady=4)
        self.password = ttk.Entry(box, width=28, show="*")
        self.password.grid(row=3, column=1, pady=4)
        device = get_device_id()
        trusted = db.get_setting("trusted_admin_device_id", "") == device
        device_text = "This PC is recognized as the trusted administrator device." if trusted else "This PC is not the original trusted administrator device."
        ttk.Label(box, text=device_text, background=CARD_BG, foreground=ACCENT if trusted else WARNING, wraplength=360).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8,8))
        btns = ttk.Frame(box, style="Card.TFrame")
        btns.grid(row=5, column=0, columnspan=2, sticky="e", pady=(8,0))
        ttk.Button(btns, text="Login", style="Accent.TButton", command=self.login).pack(side="right", padx=4)
        ttk.Button(btns, text="Cancel", command=self.cancel).pack(side="right", padx=4)
        self.username.insert(0, "admin")
        self.password.focus_set()
        self.bind("<Return>", lambda e: self.login())
        self.update_idletasks()
        x = parent.winfo_screenwidth()//2 - self.winfo_width()//2
        y = parent.winfo_screenheight()//2 - self.winfo_height()//2
        self.geometry(f"+{x}+{y}")

    def login(self):
        username = self.username.get().strip()
        password = self.password.get()
        row = self.db.one("SELECT * FROM users WHERE username=?", (username,))
        if not row or not row["active"] or not verify_password(password, row["salt"], row["password_hash"]):
            messagebox.showerror("Login failed", "Invalid username/password or inactive account.")
            return
        self.db.execute("UPDATE users SET last_login=? WHERE id=?", (iso_now(), row["id"]))
        self.result = dict(row)
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


class DarkApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1320x820")
        self.minsize(1120, 700)
        self.configure(bg=DARK_BG)
        self.db = Database(DB_PATH)
        self.withdraw()
        login = LoginDialog(self, self.db)
        self.wait_window(login)
        if not login.result:
            self.destroy()
            raise SystemExit
        self.current_user = login.result
        self.deiconify()
        self.selected_job_id = None
        self.selected_customer_id = None
        self.selected_worker_id = None
        self.style = ttk.Style(self)
        self.setup_style()
        self.build_layout()
        self.refresh_all()

    def launch_web_ui(self):
        if not open_web_dashboard:
            messagebox.showwarning("Unavailable", "Web dashboard helper could not load.")
            return
        ok, msg = open_web_dashboard("/login")
        if not ok:
            messagebox.showinfo("Web Dashboard", msg)

    def setup_style(self):
        self.style = ttk.Style(self)
        if configure_ttk:
            configure_ttk(self.style)
            return
        self.style.theme_use("clam")
        self.style.configure("TFrame", background=DARK_BG)
        self.style.configure("Panel.TFrame", background=PANEL_BG)
        self.style.configure("Card.TFrame", background=CARD_BG)
        self.style.configure("TLabel", background=DARK_BG, foreground=TEXT, font=("Segoe UI", 10))
        self.style.configure("Muted.TLabel", background=DARK_BG, foreground=MUTED)
        self.style.configure("Title.TLabel", background=DARK_BG, foreground=TEXT, font=("Segoe UI", 22, "bold"))
        self.style.configure("Header.TLabel", background=PANEL_BG, foreground=TEXT, font=("Segoe UI", 14, "bold"))
        self.style.configure("CardHeader.TLabel", background=CARD_BG, foreground=TEXT, font=("Segoe UI", 12, "bold"))
        self.style.configure("TButton", background=CARD_BG, foreground=TEXT, borderwidth=0, focusthickness=3, focuscolor=ACCENT, font=("Segoe UI", 10))
        self.style.map("TButton", background=[("active", "#334155")])
        self.style.configure("Accent.TButton", background=ACCENT, foreground="#052e16", font=("Segoe UI", 10, "bold"))
        self.style.map("Accent.TButton", background=[("active", "#2dd4bf")])
        self.style.configure("Danger.TButton", background=DANGER, foreground="white")
        self.style.map("Danger.TButton", background=[("active", "#b91c1c")])
        self.style.configure("Treeview", background="#0b1220", foreground=TEXT, fieldbackground="#0b1220", rowheight=28, borderwidth=0)
        self.style.map("Treeview", background=[("selected", "#075985")])
        self.style.configure("Treeview.Heading", background="#111827", foreground=TEXT, font=("Segoe UI", 10, "bold"))
        self.style.configure("TNotebook", background=DARK_BG, borderwidth=0)
        self.style.configure("TNotebook.Tab", background=PANEL_BG, foreground=MUTED, padding=[14, 8], font=("Segoe UI", 10, "bold"))
        self.style.map("TNotebook.Tab", background=[("selected", CARD_BG)], foreground=[("selected", TEXT)])
        self.style.configure("TEntry", fieldbackground="#0b1220", foreground=TEXT, insertcolor=TEXT)
        self.style.configure("TCombobox", fieldbackground="#0b1220", background="#0b1220", foreground=TEXT)

    def build_layout(self):
        top = ttk.Frame(self, style="Panel.TFrame", padding=14)
        top.pack(fill="x")
        ttk.Label(top, text="J and R Construction Manager", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text=f"  {PHONE}  |  Owner: Jacob Cosentino  |  Logged in: {self.current_user.get('username', '')}  |  {now_stamp()}", style="Muted.TLabel").pack(side="left", padx=12)
        if open_web_dashboard:
            ttk.Button(top, text="Web Dashboard", style="Info.TButton", command=self.launch_web_ui).pack(side="right", padx=4)
        ttk.Button(top, text="Backup ZIP", style="Accent.TButton", command=self.make_backup).pack(side="right", padx=4)
        ttk.Button(top, text="Export Reports", command=self.export_all_reports).pack(side="right", padx=4)
        ttk.Button(top, text="Refresh", command=self.refresh_all).pack(side="right", padx=4)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=10)
        self.dashboard_tab = ttk.Frame(self.nb)
        self.jobs_tab = ttk.Frame(self.nb)
        self.docs_tab = ttk.Frame(self.nb)
        self.expenses_tab = ttk.Frame(self.nb)
        self.workers_tab = ttk.Frame(self.nb)
        self.tax_tab = ttk.Frame(self.nb)
        self.evidence_tab = ttk.Frame(self.nb)
        self.log_tab = ttk.Frame(self.nb)
        self.cloud_tab = ttk.Frame(self.nb)
        self.admin_tab = ttk.Frame(self.nb)
        for tab, name in [
            (self.dashboard_tab, "Dashboard"),
            (self.jobs_tab, "Jobs & Customers"),
            (self.docs_tab, "Invoices / Estimates"),
            (self.expenses_tab, "Expenses"),
            (self.workers_tab, "Workers"),
            (self.tax_tab, "Tax Prep"),
            (self.evidence_tab, "Evidence"),
            (self.log_tab, "Business Log"),
            (self.cloud_tab, "Dropbox / Remote"),
        ]:
            self.nb.add(tab, text=name)

        self.build_dashboard()
        self.build_jobs()
        self.build_documents()
        self.build_expenses()
        self.build_workers()
        self.build_tax()
        self.build_evidence()
        self.build_log()
        self.build_cloud()
        if self.current_user.get("role") == "Admin":
            self.nb.add(self.admin_tab, text="Admin")
            self.build_admin()

    def card(self, parent, title):
        frame = ttk.Frame(parent, style="Card.TFrame", padding=12)
        ttk.Label(frame, text=title, style="CardHeader.TLabel").pack(anchor="w")
        return frame

    def build_dashboard(self):
        wrap = ttk.Frame(self.dashboard_tab)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        metrics = ttk.Frame(wrap)
        metrics.pack(fill="x")
        self.metric_labels = {}
        for key in ["Revenue", "Expenses", "Profit", "Open Balance", "Active Jobs"]:
            c = self.card(metrics, key)
            c.pack(side="left", fill="both", expand=True, padx=6, pady=6)
            lab = ttk.Label(c, text="$0.00", background=CARD_BG, foreground=ACCENT_2, font=("Segoe UI", 18, "bold"))
            lab.pack(anchor="w", pady=(10, 0))
            self.metric_labels[key] = lab

        lower = ttk.Frame(wrap)
        lower.pack(fill="both", expand=True, pady=6)
        left = self.card(lower, "Active / Pending Jobs")
        left.pack(side="left", fill="both", expand=True, padx=6)
        self.dashboard_jobs = self.make_tree(left, ["ID", "Job", "Customer", "Status", "Price", "Balance"], height=15)
        right = self.card(lower, "Alerts & Next Actions")
        right.pack(side="left", fill="both", expand=True, padx=6)
        self.alert_text = tk.Text(right, height=18, bg="#0b1220", fg=TEXT, insertbackground=TEXT, wrap="word", relief="flat")
        self.alert_text.pack(fill="both", expand=True, pady=8)

    def make_tree(self, parent, cols, height=12):
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=height)
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=120, anchor="w")
        tree.pack(fill="both", expand=True, pady=8)
        return tree

    def form_row(self, parent, label, widget, row):
        ttk.Label(parent, text=label, background=CARD_BG).grid(row=row, column=0, sticky="w", padx=4, pady=4)
        widget.grid(row=row, column=1, sticky="ew", padx=4, pady=4)

    def entry(self, parent):
        e = ttk.Entry(parent)
        return e

    def combo(self, parent, values):
        cb = ttk.Combobox(parent, values=values, state="readonly")
        if values:
            cb.set(values[0])
        return cb

    def build_jobs(self):
        wrap = ttk.Panedwindow(self.jobs_tab, orient="horizontal")
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        left = ttk.Frame(wrap)
        right = ttk.Frame(wrap)
        wrap.add(left, weight=3)
        wrap.add(right, weight=2)

        jobs_card = self.card(left, "Jobs")
        jobs_card.pack(fill="both", expand=True, padx=4, pady=4)
        btns = ttk.Frame(jobs_card, style="Card.TFrame")
        btns.pack(fill="x")
        ttk.Button(btns, text="New Job", style="Accent.TButton", command=self.new_job_window).pack(side="left", padx=3)
        ttk.Button(btns, text="Edit Selected", command=self.edit_selected_job).pack(side="left", padx=3)
        ttk.Button(btns, text="Close Paid", command=lambda: self.set_job_status("Closed Paid")).pack(side="left", padx=3)
        ttk.Button(btns, text="Closeout Checklist", command=self.show_closeout).pack(side="left", padx=3)
        self.jobs_tree = self.make_tree(jobs_card, ["ID", "Job", "Customer", "Status", "Price", "Paid", "Balance"], height=22)
        self.jobs_tree.bind("<<TreeviewSelect>>", self.on_job_select)

        customers_card = self.card(right, "Customers")
        customers_card.pack(fill="both", expand=True, padx=4, pady=4)
        cbtns = ttk.Frame(customers_card, style="Card.TFrame")
        cbtns.pack(fill="x")
        ttk.Button(cbtns, text="New Customer", style="Accent.TButton", command=self.new_customer_window).pack(side="left", padx=3)
        ttk.Button(cbtns, text="Edit Selected", command=self.edit_selected_customer).pack(side="left", padx=3)
        self.customers_tree = self.make_tree(customers_card, ["ID", "Name", "Phone", "Address"], height=16)
        self.customers_tree.bind("<<TreeviewSelect>>", self.on_customer_select)

    def build_documents(self):
        wrap = ttk.Frame(self.docs_tab)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        c = self.card(wrap, "Create Branded Estimates / Invoices")
        c.pack(fill="x", padx=4, pady=4)
        row = ttk.Frame(c, style="Card.TFrame")
        row.pack(fill="x", pady=6)
        ttk.Button(row, text="New Estimate from Selected Job", style="Accent.TButton", command=lambda: self.document_window("Estimate")).pack(side="left", padx=4)
        ttk.Button(row, text="New Invoice from Selected Job", style="Accent.TButton", command=lambda: self.document_window("Invoice")).pack(side="left", padx=4)
        ttk.Button(row, text="Open Exports Folder", command=self.open_exports).pack(side="left", padx=4)
        list_card = self.card(wrap, "Document History")
        list_card.pack(fill="both", expand=True, padx=4, pady=4)
        self.docs_tree = self.make_tree(list_card, ["ID", "Job", "Type", "Date", "Price", "File"], height=20)

    def build_expenses(self):
        wrap = ttk.Frame(self.expenses_tab)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        c = self.card(wrap, "Expenses / Receipts")
        c.pack(fill="both", expand=True, padx=4, pady=4)
        btns = ttk.Frame(c, style="Card.TFrame")
        btns.pack(fill="x")
        ttk.Button(btns, text="Add Expense", style="Accent.TButton", command=self.expense_window).pack(side="left", padx=3)
        ttk.Button(btns, text="Export Expense CSV", command=self.export_expenses_csv).pack(side="left", padx=3)
        self.expenses_tree = self.make_tree(c, ["ID", "Date", "Job", "Category", "Vendor", "Description", "Amount", "Receipt"], height=24)

    def build_workers(self):
        wrap = ttk.Panedwindow(self.workers_tab, orient="horizontal")
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        left = ttk.Frame(wrap)
        right = ttk.Frame(wrap)
        wrap.add(left, weight=2)
        wrap.add(right, weight=3)
        wc = self.card(left, "Workers / Helpers")
        wc.pack(fill="both", expand=True, padx=4, pady=4)
        b = ttk.Frame(wc, style="Card.TFrame")
        b.pack(fill="x")
        ttk.Button(b, text="Add Worker", style="Accent.TButton", command=self.worker_window).pack(side="left", padx=3)
        ttk.Button(b, text="Edit Worker", command=self.edit_selected_worker).pack(side="left", padx=3)
        self.workers_tree = self.make_tree(wc, ["ID", "Name", "W-9", "Default Rate"], height=20)
        self.workers_tree.bind("<<TreeviewSelect>>", self.on_worker_select)

        pc = self.card(right, "Worker Payments")
        pc.pack(fill="both", expand=True, padx=4, pady=4)
        pb = ttk.Frame(pc, style="Card.TFrame")
        pb.pack(fill="x")
        ttk.Button(pb, text="Add Payment", style="Accent.TButton", command=self.worker_payment_window).pack(side="left", padx=3)
        ttk.Button(pb, text="1099 Prep Export", command=self.export_worker_1099_csv).pack(side="left", padx=3)
        self.worker_payments_tree = self.make_tree(pc, ["ID", "Date", "Worker", "Job", "Amount", "Method", "Description"], height=20)

    def build_tax(self):
        wrap = ttk.Frame(self.tax_tab)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        top = self.card(wrap, "Schedule C-style Tax Prep Dashboard")
        top.pack(fill="x", padx=4, pady=4)
        self.tax_summary_text = tk.Text(top, height=12, bg="#0b1220", fg=TEXT, insertbackground=TEXT, wrap="word", relief="flat")
        self.tax_summary_text.pack(fill="x", expand=True, pady=8)
        b = ttk.Frame(top, style="Card.TFrame")
        b.pack(fill="x")
        ttk.Button(b, text="Export Schedule C Prep CSV", style="Accent.TButton", command=self.export_schedule_c_csv).pack(side="left", padx=3)
        ttk.Button(b, text="Export All Tax Files", command=self.export_tax_files).pack(side="left", padx=3)
        bottom = self.card(wrap, "Tax Category Breakdown")
        bottom.pack(fill="both", expand=True, padx=4, pady=4)
        self.tax_tree = self.make_tree(bottom, ["Category", "Amount", "Notes"], height=16)

    def build_evidence(self):
        wrap = ttk.Frame(self.evidence_tab)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        c = self.card(wrap, "Evidence / Receipt Index")
        c.pack(fill="both", expand=True, padx=4, pady=4)
        b = ttk.Frame(c, style="Card.TFrame")
        b.pack(fill="x")
        ttk.Button(b, text="Add Evidence", style="Accent.TButton", command=self.evidence_window).pack(side="left", padx=3)
        ttk.Button(b, text="Copy File Into Evidence Folder", command=self.copy_evidence_file).pack(side="left", padx=3)
        ttk.Button(b, text="Open Evidence Folder", command=lambda: self.open_path(EVIDENCE_DIR)).pack(side="left", padx=3)
        self.evidence_tree = self.make_tree(c, ["ID", "Date", "Job", "Type", "File", "Description"], height=23)

    def build_log(self):
        wrap = ttk.Frame(self.log_tab)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        c = self.card(wrap, "Timestamped Business Log")
        c.pack(fill="both", expand=True, padx=4, pady=4)
        b = ttk.Frame(c, style="Card.TFrame")
        b.pack(fill="x")
        ttk.Button(b, text="Add Log Entry", style="Accent.TButton", command=self.log_window).pack(side="left", padx=3)
        self.log_tree = self.make_tree(c, ["ID", "Timestamp", "Category", "Entry"], height=24)

    def build_cloud(self):
        wrap = ttk.Frame(self.cloud_tab)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        c = self.card(wrap, "Dropbox / Remote Access Setup")
        c.pack(fill="x", padx=4, pady=4)
        info = ("Best secure setup: install Dropbox Desktop and point this program to your local Dropbox-synced J&R folder. "
                "This lets the program store backups, exports, evidence indexes, and working files where Dropbox syncs them. "
                "For true live multi-user use, use a VPN/Tailscale or a hosted server before opening anything to the internet.")
        ttk.Label(c, text=info, background=CARD_BG, foreground=TEXT, wraplength=1050).pack(anchor="w", pady=(6,10))
        row = ttk.Frame(c, style="Card.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Local Dropbox business folder:", background=CARD_BG).pack(side="left", padx=4)
        self.dropbox_path_var = tk.StringVar(value=self.db.get_setting("dropbox_folder", ""))
        ttk.Entry(row, textvariable=self.dropbox_path_var, width=85).pack(side="left", padx=4, fill="x", expand=True)
        ttk.Button(row, text="Browse", command=self.choose_dropbox_folder).pack(side="left", padx=4)
        ttk.Button(row, text="Save", style="Accent.TButton", command=self.save_dropbox_folder).pack(side="left", padx=4)
        actions = ttk.Frame(c, style="Card.TFrame")
        actions.pack(fill="x", pady=10)
        ttk.Button(actions, text="Sync Backup to Dropbox Folder", style="Accent.TButton", command=self.sync_backup_to_dropbox).pack(side="left", padx=4)
        ttk.Button(actions, text="Export Account Index", command=self.export_user_index).pack(side="left", padx=4)
        ttk.Button(actions, text="Open Dropbox Folder", command=self.open_dropbox_folder).pack(side="left", padx=4)
        warn = self.card(wrap, "Security Notes")
        warn.pack(fill="both", expand=True, padx=4, pady=4)
        self.cloud_text = tk.Text(warn, height=16, bg="#0b1220", fg=TEXT, insertbackground=TEXT, wrap="word", relief="flat")
        self.cloud_text.pack(fill="both", expand=True, pady=8)
        self.cloud_text.insert("end", "Remote users: do not share the admin password. Create separate user accounts for each person.\n\n")
        self.cloud_text.insert("end", "The default admin/admin login exists because you requested it, but it should be changed immediately after install.\n\n")
        self.cloud_text.insert("end", "This version stores hashed passwords in the database, not readable password spreadsheets. The account index export intentionally does not reveal passwords.\n\n")
        self.cloud_text.insert("end", "If you want true simultaneous internet users, the next upgrade should be a server edition with HTTPS, per-user permissions, and automatic conflict-safe database handling. SQLite in Dropbox is fine for backup/sync, but not ideal for many people editing at the exact same time.")
        self.cloud_text.config(state="disabled")

    def choose_dropbox_folder(self):
        folder = filedialog.askdirectory(title="Choose local Dropbox J&R business folder")
        if folder:
            self.dropbox_path_var.set(folder)

    def save_dropbox_folder(self):
        folder = self.dropbox_path_var.get().strip()
        self.db.set_setting("dropbox_folder", folder)
        self.db.log("Dropbox", f"Dropbox folder set to {folder}")
        if folder:
            ensure_dropbox_organization(folder)
        messagebox.showinfo("Saved", "Dropbox folder setting saved.")

    def open_dropbox_folder(self):
        folder = self.db.get_setting("dropbox_folder", "")
        if not folder:
            messagebox.showwarning("Missing folder", "Set the Dropbox folder first.")
            return
        self.open_path(Path(folder))

    def sync_backup_to_dropbox(self):
        folder = self.db.get_setting("dropbox_folder", "")
        if not folder:
            messagebox.showwarning("Missing folder", "Set the Dropbox folder first.")
            return
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        self.export_all_reports()
        stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        target = folder / f"J_and_R_Construction_Manager_Backup_{stamp}.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            for p in [DB_PATH, Path(__file__).resolve(), BASE_DIR / "README.txt", BASE_DIR / "START_HERE.txt"]:
                if p.exists():
                    z.write(p, p.relative_to(BASE_DIR))
            for out in EXPORT_DIR.rglob("*"):
                if out.is_file():
                    z.write(out, Path("exports") / out.name)
            for ev in EVIDENCE_DIR.rglob("*"):
                if ev.is_file():
                    z.write(ev, Path("evidence") / ev.name)
            z.writestr("BACKUP_MANIFEST.txt", f"J and R Construction Manager backup created {now_stamp()}\nOwner: Jacob Cosentino\nTrusted device: {get_device_id()}\n")
        self.db.log("Dropbox", f"Created Dropbox backup {target.name}")
        messagebox.showinfo("Backup Synced", f"Backup copied to Dropbox folder:\n{target}")

    def build_admin(self):
        wrap = ttk.Frame(self.admin_tab)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        c = self.card(wrap, "Admin Accounts")
        c.pack(fill="both", expand=True, padx=4, pady=4)
        btns = ttk.Frame(c, style="Card.TFrame")
        btns.pack(fill="x")
        ttk.Button(btns, text="Add User", style="Accent.TButton", command=self.add_user_window).pack(side="left", padx=3)
        ttk.Button(btns, text="Reset Password", command=self.reset_user_password).pack(side="left", padx=3)
        ttk.Button(btns, text="Toggle Active", command=self.toggle_user_active).pack(side="left", padx=3)
        ttk.Button(btns, text="Export Account Index", command=self.export_user_index).pack(side="left", padx=3)
        self.users_tree = self.make_tree(c, ["ID", "Username", "Full Name", "Role", "Active", "Last Login"], height=22)
        self.refresh_users()

    def refresh_users(self):
        if not hasattr(self, "users_tree"):
            return
        self.clear_tree(self.users_tree)
        rows = self.db.q("SELECT id, username, full_name, role, active, last_login FROM users ORDER BY username")
        for r in rows:
            self.users_tree.insert("", "end", values=[r["id"], r["username"], r["full_name"] or "", r["role"], "Yes" if r["active"] else "No", r["last_login"] or ""])

    def selected_user_id(self):
        sel = getattr(self, "users_tree", None).selection() if hasattr(self, "users_tree") else []
        if not sel:
            messagebox.showwarning("Select user", "Select a user first.")
            return None
        return int(self.users_tree.item(sel[0], "values")[0])

    def add_user_window(self):
        win = tk.Toplevel(self)
        win.title("Add User")
        win.configure(bg=DARK_BG)
        f = ttk.Frame(win, style="Card.TFrame", padding=14)
        f.pack(fill="both", expand=True, padx=10, pady=10)
        vals = {}
        for i, label in enumerate(["Username", "Full Name", "Password"]):
            ttk.Label(f, text=label, background=CARD_BG).grid(row=i, column=0, sticky="w", padx=4, pady=4)
            e = ttk.Entry(f, show="*" if label == "Password" else "")
            e.grid(row=i, column=1, sticky="ew", padx=4, pady=4)
            vals[label] = e
        ttk.Label(f, text="Role", background=CARD_BG).grid(row=3, column=0, sticky="w", padx=4, pady=4)
        role = ttk.Combobox(f, values=["Admin", "User"], state="readonly")
        role.set("User")
        role.grid(row=3, column=1, sticky="ew", padx=4, pady=4)
        def save():
            username = vals["Username"].get().strip()
            pw = vals["Password"].get()
            if not username or not pw:
                messagebox.showerror("Missing", "Username and password are required.")
                return
            salt, ph = hash_password(pw)
            try:
                self.db.execute("INSERT INTO users(username, full_name, role, salt, password_hash, active, created_at) VALUES(?,?,?,?,?,?,?)", (username, vals["Full Name"].get().strip(), role.get(), salt, ph, 1, iso_now()))
                self.db.log("Admin", f"User account added: {username} ({role.get()}).")
                win.destroy(); self.refresh_users()
            except sqlite3.IntegrityError:
                messagebox.showerror("Exists", "That username already exists.")
        ttk.Button(f, text="Save User", style="Accent.TButton", command=save).grid(row=4, column=1, sticky="e", pady=8)
        f.columnconfigure(1, weight=1)

    def reset_user_password(self):
        uid = self.selected_user_id()
        if not uid: return
        win = tk.Toplevel(self)
        win.title("Reset Password")
        win.configure(bg=DARK_BG)
        f = ttk.Frame(win, style="Card.TFrame", padding=14)
        f.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Label(f, text="New Password", background=CARD_BG).grid(row=0, column=0, padx=4, pady=4)
        pw = ttk.Entry(f, show="*")
        pw.grid(row=0, column=1, padx=4, pady=4)
        def save():
            if not pw.get():
                messagebox.showerror("Missing", "Password required."); return
            salt, ph = hash_password(pw.get())
            self.db.execute("UPDATE users SET salt=?, password_hash=?, must_change_password=1 WHERE id=?", (salt, ph, uid))
            self.db.log("Admin", f"Password reset for user ID {uid}.")
            win.destroy(); self.refresh_users()
        ttk.Button(f, text="Reset", style="Accent.TButton", command=save).grid(row=1, column=1, sticky="e", pady=8)

    def toggle_user_active(self):
        uid = self.selected_user_id()
        if not uid: return
        row = self.db.one("SELECT username, active FROM users WHERE id=?", (uid,))
        if row and row["username"] == "admin" and row["active"]:
            messagebox.showwarning("Protected", "The default admin account cannot be disabled from here.")
            return
        self.db.execute("UPDATE users SET active=CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?", (uid,))
        self.db.log("Admin", f"Toggled active status for user ID {uid}.")
        self.refresh_users()

    def export_user_index(self):
        path = EXPORT_DIR / "JRC_User_Accounts_Admin_Index.csv"
        rows = self.db.q("SELECT username, full_name, role, active, created_at, last_login, notes FROM users ORDER BY username")
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Username", "Full Name", "Role", "Active", "Created", "Last Login", "Password Storage", "Notes"])
            for r in rows:
                w.writerow([r["username"], r["full_name"] or "", r["role"], "Yes" if r["active"] else "No", r["created_at"], r["last_login"] or "", "Hashed in SQLite database - not plain text", r["notes"] or ""])
        messagebox.showinfo("Exported", str(path))

    def refresh_all(self):
        self.refresh_customers()
        self.refresh_jobs()
        self.refresh_documents()
        self.refresh_expenses()
        self.refresh_workers()
        self.refresh_worker_payments()
        self.refresh_tax()
        self.refresh_evidence()
        self.refresh_log()
        self.refresh_dashboard()

    def clear_tree(self, tree):
        for item in tree.get_children():
            tree.delete(item)

    def job_label_map(self):
        rows = self.db.q("SELECT j.id, j.job_name, COALESCE(c.name,'') AS customer FROM jobs j LEFT JOIN customers c ON c.id=j.customer_id ORDER BY j.id DESC")
        return {f"{r['id']} - {r['job_name']} ({r['customer']})": r['id'] for r in rows}

    def customer_label_map(self):
        rows = self.db.q("SELECT id, name FROM customers ORDER BY name")
        return {f"{r['id']} - {r['name']}": r['id'] for r in rows}

    def worker_label_map(self):
        rows = self.db.q("SELECT id, name FROM workers ORDER BY name")
        return {f"{r['id']} - {r['name']}": r['id'] for r in rows}

    def refresh_customers(self):
        self.clear_tree(self.customers_tree)
        for r in self.db.q("SELECT * FROM customers ORDER BY name"):
            self.customers_tree.insert("", "end", values=(r["id"], r["name"], r["phone"] or "", r["address"] or ""))

    def refresh_jobs(self):
        self.clear_tree(self.jobs_tree)
        sql = """
        SELECT j.*, COALESCE(c.name,'') AS customer,
               (COALESCE(j.deposit_paid,0)+COALESCE(j.balance_paid,0)) AS paid,
               (COALESCE(j.contract_price,0)-COALESCE(j.deposit_paid,0)-COALESCE(j.balance_paid,0)) AS balance
        FROM jobs j LEFT JOIN customers c ON c.id=j.customer_id
        ORDER BY j.updated_at DESC
        """
        for r in self.db.q(sql):
            self.jobs_tree.insert("", "end", values=(r["id"], r["job_name"], r["customer"], r["status"], money(r["contract_price"]), money(r["paid"]), money(r["balance"])))

    def refresh_documents(self):
        self.clear_tree(self.docs_tree)
        sql = """
        SELECT d.*, j.job_name FROM documents d JOIN jobs j ON j.id=d.job_id ORDER BY d.id DESC
        """
        for r in self.db.q(sql):
            self.docs_tree.insert("", "end", values=(r["id"], r["job_name"], r["doc_type"], r["date"], money(r["price"]), r["file_path"] or ""))

    def refresh_expenses(self):
        self.clear_tree(self.expenses_tree)
        sql = """
        SELECT e.*, COALESCE(j.job_name,'') AS job FROM expenses e LEFT JOIN jobs j ON j.id=e.job_id ORDER BY e.date DESC, e.id DESC
        """
        for r in self.db.q(sql):
            self.expenses_tree.insert("", "end", values=(r["id"], r["date"], r["job"], r["category"], r["vendor"] or "", r["description"], money(r["amount"]), r["receipt_status"] or ""))

    def refresh_workers(self):
        self.clear_tree(self.workers_tree)
        for r in self.db.q("SELECT * FROM workers ORDER BY name"):
            self.workers_tree.insert("", "end", values=(r["id"], r["name"], r["w9_status"], money(r["default_day_rate"])))

    def refresh_worker_payments(self):
        self.clear_tree(self.worker_payments_tree)
        sql = """
        SELECT p.*, w.name AS worker, COALESCE(j.job_name,'') AS job
        FROM worker_payments p
        JOIN workers w ON w.id=p.worker_id
        LEFT JOIN jobs j ON j.id=p.job_id
        ORDER BY p.date DESC, p.id DESC
        """
        for r in self.db.q(sql):
            self.worker_payments_tree.insert("", "end", values=(r["id"], r["date"], r["worker"], r["job"], money(r["amount"]), r["payment_method"] or "", r["work_description"] or ""))

    def refresh_evidence(self):
        self.clear_tree(self.evidence_tree)
        sql = """
        SELECT e.*, COALESCE(j.job_name,'') AS job FROM evidence e LEFT JOIN jobs j ON j.id=e.job_id ORDER BY e.date DESC, e.id DESC
        """
        for r in self.db.q(sql):
            self.evidence_tree.insert("", "end", values=(r["id"], r["date"], r["job"], r["evidence_type"] or "", r["file_name"], r["description"] or ""))

    def refresh_log(self):
        self.clear_tree(self.log_tree)
        for r in self.db.q("SELECT * FROM business_log ORDER BY id DESC LIMIT 500"):
            self.log_tree.insert("", "end", values=(r["id"], r["timestamp"], r["category"], r["entry"]))

    def refresh_tax(self):
        income = self.db.one("SELECT SUM(CASE WHEN status LIKE 'Closed Paid' OR deposit_paid+balance_paid > 0 THEN deposit_paid+balance_paid ELSE 0 END) AS total FROM jobs")
        revenue = income["total"] or 0
        expenses_by_cat = self.db.q("SELECT category, SUM(amount) AS total FROM expenses GROUP BY category")
        helper = self.db.one("SELECT SUM(amount) AS total FROM worker_payments WHERE status='Paid'")
        helper_total = helper["total"] or 0
        total_exp = sum((r["total"] or 0) for r in expenses_by_cat) + helper_total
        profit = revenue - total_exp

        self.tax_summary_text.delete("1.0", "end")
        msg = f"""J&R Construction Schedule C-Style Prep Summary\nGenerated: {now_stamp()}\n\nConfirmed money received: {money(revenue)}\nTracked expenses: {money(total_exp)}\nEstimated net business profit: {money(profit)}\n\nImportant: Owner labor is job-costing only. It is not a deductible wage to yourself as a sole proprietor. Cash payments are business income when received. Use a CPA/tax preparer for final filing decisions.\n"""
        self.tax_summary_text.insert("end", msg)

        self.clear_tree(self.tax_tree)
        for r in expenses_by_cat:
            self.tax_tree.insert("", "end", values=(r["category"], money(r["total"] or 0), "Expense category"))
        self.tax_tree.insert("", "end", values=("Worker/Helper Pay", money(helper_total), "Tracked from worker payments"))
        self.tax_tree.insert("", "end", values=("Estimated Net Profit", money(profit), "Revenue minus tracked expenses"))

    def refresh_dashboard(self):
        revenue = self.db.one("SELECT SUM(deposit_paid+balance_paid) AS total FROM jobs")["total"] or 0
        exp = self.db.one("SELECT SUM(amount) AS total FROM expenses")["total"] or 0
        helper = self.db.one("SELECT SUM(amount) AS total FROM worker_payments WHERE status='Paid'")["total"] or 0
        expenses = exp + helper
        profit = revenue - expenses
        open_balance = self.db.one("SELECT SUM(contract_price-deposit_paid-balance_paid) AS total FROM jobs WHERE status NOT LIKE 'Closed Paid'")["total"] or 0
        active_jobs = self.db.one("SELECT COUNT(*) AS total FROM jobs WHERE status IN ('Lead','Estimate Sent','Approved','Active','Waiting Payment','On Hold')")["total"] or 0
        vals = {"Revenue": money(revenue), "Expenses": money(expenses), "Profit": money(profit), "Open Balance": money(open_balance), "Active Jobs": str(active_jobs)}
        for k, v in vals.items():
            self.metric_labels[k].config(text=v)
        self.clear_tree(self.dashboard_jobs)
        sql = """
        SELECT j.id, j.job_name, COALESCE(c.name,'') customer, j.status, j.contract_price,
               (j.contract_price-j.deposit_paid-j.balance_paid) AS balance
        FROM jobs j LEFT JOIN customers c ON c.id=j.customer_id
        WHERE j.status NOT LIKE 'Closed Paid'
        ORDER BY j.updated_at DESC LIMIT 20
        """
        for r in self.db.q(sql):
            self.dashboard_jobs.insert("", "end", values=(r["id"], r["job_name"], r["customer"], r["status"], money(r["contract_price"]), money(r["balance"])))
        alerts = []
        for r in self.db.q("SELECT job_name, status, contract_price, deposit_paid, balance_paid, callback_flag FROM jobs ORDER BY updated_at DESC LIMIT 50"):
            if r["callback_flag"]:
                alerts.append(f"CALLBACK FLAG: {r['job_name']}")
            balance = (r["contract_price"] or 0) - (r["deposit_paid"] or 0) - (r["balance_paid"] or 0)
            if balance > 0 and r["status"] in ("Active", "Waiting Payment", "Closed Unpaid"):
                alerts.append(f"Balance due: {r['job_name']} - {money(balance)}")
        for r in self.db.q("SELECT name, w9_status FROM workers WHERE w9_status!='Received' ORDER BY name"):
            alerts.append(f"Worker W-9 needed/review: {r['name']} - {r['w9_status']}")
        self.alert_text.delete("1.0", "end")
        self.alert_text.insert("end", "\n".join(alerts) if alerts else "No urgent alerts. Keep logging receipts and payments as they happen.")

    def selected_id(self, tree):
        sel = tree.selection()
        if not sel:
            return None
        return int(tree.item(sel[0], "values")[0])

    def on_job_select(self, event=None):
        self.selected_job_id = self.selected_id(self.jobs_tree)

    def on_customer_select(self, event=None):
        self.selected_customer_id = self.selected_id(self.customers_tree)

    def on_worker_select(self, event=None):
        self.selected_worker_id = self.selected_id(self.workers_tree)

    def new_customer_window(self, existing=None):
        win = tk.Toplevel(self)
        win.title("Customer")
        win.configure(bg=CARD_BG)
        frm = ttk.Frame(win, style="Card.TFrame", padding=12)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)
        data = existing or {}
        fields = {}
        for i, key in enumerate(["name", "phone", "email", "address", "notes"]):
            if key == "notes":
                w = tk.Text(frm, height=4, bg="#0b1220", fg=TEXT, insertbackground=TEXT)
                w.insert("1.0", data.get(key, "") or "")
            else:
                w = self.entry(frm)
                w.insert(0, data.get(key, "") or "")
            self.form_row(frm, key.title(), w, i)
            fields[key] = w

        def save():
            vals = {k: (v.get("1.0", "end").strip() if isinstance(v, tk.Text) else v.get().strip()) for k, v in fields.items()}
            if not vals["name"]:
                messagebox.showerror("Missing", "Customer name is required.")
                return
            if existing:
                self.db.execute("UPDATE customers SET name=?, phone=?, email=?, address=?, notes=? WHERE id=?", (vals["name"], vals["phone"], vals["email"], vals["address"], vals["notes"], existing["id"]))
                self.db.log("Customer", f"Updated customer {vals['name']}.")
            else:
                self.db.execute("INSERT INTO customers(name, phone, email, address, notes, created_at) VALUES(?,?,?,?,?,?)", (vals["name"], vals["phone"], vals["email"], vals["address"], vals["notes"], iso_now()))
                self.db.log("Customer", f"Added customer {vals['name']}.")
            win.destroy(); self.refresh_all()
        ttk.Button(frm, text="Save", style="Accent.TButton", command=save).grid(row=6, column=0, columnspan=2, pady=10)

    def edit_selected_customer(self):
        cid = self.selected_id(self.customers_tree)
        if not cid:
            messagebox.showinfo("Select", "Select a customer first.")
            return
        r = self.db.one("SELECT * FROM customers WHERE id=?", (cid,))
        self.new_customer_window(dict(r))

    def new_job_window(self, existing=None):
        win = tk.Toplevel(self)
        win.title("Job")
        win.geometry("760x720")
        win.configure(bg=CARD_BG)
        frm = ttk.Frame(win, style="Card.TFrame", padding=12)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)
        data = existing or {}
        customer_map = self.customer_label_map()
        cust = self.combo(frm, list(customer_map.keys()))
        if data.get("customer_id"):
            for label, cid in customer_map.items():
                if cid == data.get("customer_id"):
                    cust.set(label)
        self.form_row(frm, "Customer", cust, 0)
        fields = {"customer": cust}
        names = ["job_name", "job_address", "status", "contract_price", "deposit_required", "deposit_paid", "balance_paid", "payment_method", "start_date", "completion_date"]
        row = 1
        for key in names:
            if key == "status":
                w = self.combo(frm, JOB_STATUSES); w.set(data.get(key, "Lead") or "Lead")
            elif key == "payment_method":
                w = self.combo(frm, [""] + PAYMENT_METHODS); w.set(data.get(key, "") or "")
            else:
                w = self.entry(frm); w.insert(0, str(data.get(key, "") or ""))
            self.form_row(frm, key.replace("_", " ").title(), w, row)
            fields[key] = w
            row += 1
        for key, label, height in [("scope", "Scope", 6), ("notes", "Notes", 4)]:
            w = tk.Text(frm, height=height, bg="#0b1220", fg=TEXT, insertbackground=TEXT, wrap="word")
            w.insert("1.0", data.get(key, "") or "")
            ttk.Label(frm, text=label, background=CARD_BG).grid(row=row, column=0, sticky="nw", padx=4, pady=4)
            w.grid(row=row, column=1, sticky="ew", padx=4, pady=4)
            fields[key] = w
            row += 1
        callback_var = tk.IntVar(value=int(data.get("callback_flag", 0) or 0))
        cb = ttk.Checkbutton(frm, text="Callback / warranty follow-up flag", variable=callback_var)
        cb.grid(row=row, column=1, sticky="w", padx=4, pady=4)
        row += 1

        def save():
            label = fields["customer"].get()
            customer_id = customer_map.get(label)
            vals = {}
            for k, w in fields.items():
                if k == "customer": continue
                vals[k] = w.get("1.0", "end").strip() if isinstance(w, tk.Text) else w.get().strip()
            if not vals["job_name"]:
                messagebox.showerror("Missing", "Job name is required.")
                return
            nums = ["contract_price", "deposit_required", "deposit_paid", "balance_paid"]
            for n in nums:
                vals[n] = parse_money(vals[n])
            if existing:
                self.db.execute("""
                UPDATE jobs SET customer_id=?, job_name=?, job_address=?, status=?, scope=?, contract_price=?, deposit_required=?, deposit_paid=?, balance_paid=?, payment_method=?, start_date=?, completion_date=?, callback_flag=?, notes=?, updated_at=? WHERE id=?
                """, (customer_id, vals["job_name"], vals["job_address"], vals["status"], vals["scope"], vals["contract_price"], vals["deposit_required"], vals["deposit_paid"], vals["balance_paid"], vals["payment_method"], vals["start_date"], vals["completion_date"], callback_var.get(), vals["notes"], iso_now(), existing["id"]))
                self.db.log("Job", f"Updated job {vals['job_name']}.")
            else:
                self.db.execute("""
                INSERT INTO jobs(customer_id, job_name, job_address, status, scope, contract_price, deposit_required, deposit_paid, balance_paid, payment_method, start_date, completion_date, callback_flag, notes, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (customer_id, vals["job_name"], vals["job_address"], vals["status"], vals["scope"], vals["contract_price"], vals["deposit_required"], vals["deposit_paid"], vals["balance_paid"], vals["payment_method"], vals["start_date"], vals["completion_date"], callback_var.get(), vals["notes"], iso_now(), iso_now()))
                self.db.log("Job", f"Added job {vals['job_name']}.")
            win.destroy(); self.refresh_all()
        ttk.Button(frm, text="Save Job", style="Accent.TButton", command=save).grid(row=row, column=0, columnspan=2, pady=10)

    def edit_selected_job(self):
        jid = self.selected_id(self.jobs_tree)
        if not jid:
            messagebox.showinfo("Select", "Select a job first.")
            return
        r = self.db.one("SELECT * FROM jobs WHERE id=?", (jid,))
        self.new_job_window(dict(r))

    def set_job_status(self, status):
        jid = self.selected_id(self.jobs_tree)
        if not jid:
            messagebox.showinfo("Select", "Select a job first.")
            return
        self.db.execute("UPDATE jobs SET status=?, updated_at=? WHERE id=?", (status, iso_now(), jid))
        self.db.log("Job", f"Job ID {jid} marked {status}.")
        self.refresh_all()

    def show_closeout(self):
        jid = self.selected_id(self.jobs_tree)
        if not jid:
            messagebox.showinfo("Select", "Select a job first.")
            return
        j = self.db.one("SELECT * FROM jobs WHERE id=?", (jid,))
        docs = self.db.one("SELECT COUNT(*) c FROM documents WHERE job_id=?", (jid,))["c"]
        expenses = self.db.one("SELECT COUNT(*) c FROM expenses WHERE job_id=?", (jid,))["c"]
        workers = self.db.one("SELECT COUNT(*) c FROM worker_payments WHERE job_id=?", (jid,))["c"]
        evidence = self.db.one("SELECT COUNT(*) c FROM evidence WHERE job_id=?", (jid,))["c"]
        paid = (j["deposit_paid"] or 0) + (j["balance_paid"] or 0)
        balance = (j["contract_price"] or 0) - paid
        msg = f"""Closeout checklist for {j['job_name']}\n\nDocument PDF created: {'YES' if docs else 'NEEDS REVIEW'}\nExpenses/receipts logged: {'YES' if expenses else 'NEEDS REVIEW'}\nHelper payments logged: {'YES' if workers else 'None/needs review'}\nEvidence/photos indexed: {'YES' if evidence else 'NEEDS REVIEW'}\nPaid amount: {money(paid)}\nBalance: {money(balance)}\nCustomer happy / final note: add to business log\n"""
        messagebox.showinfo("Closeout Checklist", msg)

    def expense_window(self):
        win = tk.Toplevel(self); win.title("Add Expense"); win.configure(bg=CARD_BG)
        frm = ttk.Frame(win, style="Card.TFrame", padding=12); frm.pack(fill="both", expand=True); frm.columnconfigure(1, weight=1)
        job_map = self.job_label_map()
        fields = {}
        widgets = [
            ("job", self.combo(frm, [""] + list(job_map.keys()))),
            ("date", self.entry(frm)),
            ("vendor", self.entry(frm)),
            ("category", self.combo(frm, TAX_CATEGORIES)),
            ("description", self.entry(frm)),
            ("amount", self.entry(frm)),
            ("receipt_status", self.combo(frm, ["Needs receipt", "Receipt saved", "Pending receipt", "No receipt"])),
            ("notes", self.entry(frm)),
        ]
        widgets[1][1].insert(0, dt.date.today().isoformat())
        for i, (k, w) in enumerate(widgets):
            self.form_row(frm, k.replace("_", " ").title(), w, i); fields[k] = w
        def save():
            job_id = job_map.get(fields["job"].get())
            vals = {k: w.get().strip() for k,w in fields.items() if k != "job"}
            if not vals["description"]:
                messagebox.showerror("Missing", "Description is required."); return
            self.db.execute("INSERT INTO expenses(job_id, date, vendor, category, description, amount, receipt_status, notes) VALUES(?,?,?,?,?,?,?,?)", (job_id, vals["date"], vals["vendor"], vals["category"], vals["description"], parse_money(vals["amount"]), vals["receipt_status"], vals["notes"]))
            self.db.log("Expense", f"Added expense {vals['description']} - {money(parse_money(vals['amount']))}.")
            win.destroy(); self.refresh_all()
        ttk.Button(frm, text="Save Expense", style="Accent.TButton", command=save).grid(row=9, column=0, columnspan=2, pady=10)

    def worker_window(self, existing=None):
        win = tk.Toplevel(self); win.title("Worker"); win.configure(bg=CARD_BG)
        frm = ttk.Frame(win, style="Card.TFrame", padding=12); frm.pack(fill="both", expand=True); frm.columnconfigure(1, weight=1)
        data = existing or {}
        fields = {}
        for i, k in enumerate(["name", "phone", "email", "address", "w9_status", "default_day_rate", "notes"]):
            if k == "w9_status":
                w = self.combo(frm, ["Needed", "Requested", "Received", "Not required/review"]); w.set(data.get(k, "Needed") or "Needed")
            else:
                w = self.entry(frm); w.insert(0, str(data.get(k, "") or ""))
            self.form_row(frm, k.replace("_", " ").title(), w, i); fields[k] = w
        def save():
            vals = {k: w.get().strip() for k,w in fields.items()}
            if not vals["name"]:
                messagebox.showerror("Missing", "Worker name required."); return
            if existing:
                self.db.execute("UPDATE workers SET name=?, phone=?, email=?, address=?, w9_status=?, default_day_rate=?, notes=? WHERE id=?", (vals["name"], vals["phone"], vals["email"], vals["address"], vals["w9_status"], parse_money(vals["default_day_rate"]), vals["notes"], existing["id"]))
                self.db.log("Worker", f"Updated worker {vals['name']}.")
            else:
                self.db.execute("INSERT INTO workers(name, phone, email, address, w9_status, default_day_rate, notes, created_at) VALUES(?,?,?,?,?,?,?,?)", (vals["name"], vals["phone"], vals["email"], vals["address"], vals["w9_status"], parse_money(vals["default_day_rate"]), vals["notes"], iso_now()))
                self.db.log("Worker", f"Added worker {vals['name']}.")
            win.destroy(); self.refresh_all()
        ttk.Button(frm, text="Save Worker", style="Accent.TButton", command=save).grid(row=8, column=0, columnspan=2, pady=10)

    def edit_selected_worker(self):
        wid = self.selected_id(self.workers_tree)
        if not wid:
            messagebox.showinfo("Select", "Select a worker first."); return
        r = self.db.one("SELECT * FROM workers WHERE id=?", (wid,))
        self.worker_window(dict(r))

    def worker_payment_window(self):
        win = tk.Toplevel(self); win.title("Worker Payment"); win.configure(bg=CARD_BG)
        frm = ttk.Frame(win, style="Card.TFrame", padding=12); frm.pack(fill="both", expand=True); frm.columnconfigure(1, weight=1)
        worker_map = self.worker_label_map(); job_map = self.job_label_map(); fields = {}
        data = [
            ("worker", self.combo(frm, list(worker_map.keys()))),
            ("job", self.combo(frm, [""] + list(job_map.keys()))),
            ("date", self.entry(frm)),
            ("work_description", self.entry(frm)),
            ("amount", self.entry(frm)),
            ("payment_method", self.combo(frm, PAYMENT_METHODS)),
            ("status", self.combo(frm, ["Paid", "Owed", "Review"])),
            ("notes", self.entry(frm)),
        ]
        data[2][1].insert(0, dt.date.today().isoformat())
        for i, (k,w) in enumerate(data):
            self.form_row(frm, k.replace("_", " ").title(), w, i); fields[k] = w
        def save():
            wid = worker_map.get(fields["worker"].get()); jid = job_map.get(fields["job"].get())
            if not wid:
                messagebox.showerror("Missing", "Worker required."); return
            vals = {k: w.get().strip() for k,w in fields.items() if k not in ("worker","job")}
            self.db.execute("INSERT INTO worker_payments(worker_id, job_id, date, work_description, amount, payment_method, status, notes) VALUES(?,?,?,?,?,?,?,?)", (wid, jid, vals["date"], vals["work_description"], parse_money(vals["amount"]), vals["payment_method"], vals["status"], vals["notes"]))
            self.db.log("Worker Pay", f"Logged worker payment {money(parse_money(vals['amount']))}.")
            win.destroy(); self.refresh_all()
        ttk.Button(frm, text="Save Payment", style="Accent.TButton", command=save).grid(row=9, column=0, columnspan=2, pady=10)

    def evidence_window(self):
        win = tk.Toplevel(self); win.title("Evidence"); win.configure(bg=CARD_BG)
        frm = ttk.Frame(win, style="Card.TFrame", padding=12); frm.pack(fill="both", expand=True); frm.columnconfigure(1, weight=1)
        job_map = self.job_label_map(); fields = {}
        data = [
            ("job", self.combo(frm, [""] + list(job_map.keys()))),
            ("date", self.entry(frm)),
            ("file_name", self.entry(frm)),
            ("file_path", self.entry(frm)),
            ("evidence_type", self.combo(frm, ["Receipt", "Photo", "Invoice", "Estimate", "Insurance", "Tax/Admin", "Other"])),
            ("description", self.entry(frm)),
            ("notes", self.entry(frm)),
        ]
        data[1][1].insert(0, dt.date.today().isoformat())
        for i,(k,w) in enumerate(data):
            self.form_row(frm, k.replace("_", " ").title(), w, i); fields[k]=w
        def browse():
            p = filedialog.askopenfilename()
            if p:
                fields["file_path"].delete(0,"end"); fields["file_path"].insert(0,p)
                fields["file_name"].delete(0,"end"); fields["file_name"].insert(0, Path(p).name)
        ttk.Button(frm, text="Browse File", command=browse).grid(row=8, column=1, sticky="w", pady=4)
        def save():
            jid = job_map.get(fields["job"].get())
            vals = {k:w.get().strip() for k,w in fields.items() if k != "job"}
            if not vals["file_name"]:
                messagebox.showerror("Missing", "File name is required."); return
            self.db.execute("INSERT INTO evidence(job_id, date, file_name, file_path, evidence_type, description, notes) VALUES(?,?,?,?,?,?,?)", (jid, vals["date"], vals["file_name"], vals["file_path"], vals["evidence_type"], vals["description"], vals["notes"]))
            self.db.log("Evidence", f"Indexed evidence {vals['file_name']}.")
            win.destroy(); self.refresh_all()
        ttk.Button(frm, text="Save Evidence", style="Accent.TButton", command=save).grid(row=9, column=0, columnspan=2, pady=10)

    def copy_evidence_file(self):
        p = filedialog.askopenfilename(title="Choose receipt/photo/document to copy into evidence folder")
        if not p:
            return
        src = Path(p); dest = EVIDENCE_DIR / src.name
        if dest.exists():
            base, ext = dest.stem, dest.suffix
            dest = EVIDENCE_DIR / f"{base}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        shutil.copy2(src, dest)
        self.db.execute("INSERT INTO evidence(date, file_name, file_path, evidence_type, description, notes) VALUES(?,?,?,?,?,?)", (dt.date.today().isoformat(), dest.name, str(dest), "Evidence File", "Copied into evidence folder", ""))
        self.db.log("Evidence", f"Copied evidence file {dest.name}.")
        self.refresh_all()
        messagebox.showinfo("Copied", f"Copied to {dest}")

    def log_window(self):
        win = tk.Toplevel(self); win.title("Log Entry"); win.configure(bg=CARD_BG)
        frm = ttk.Frame(win, style="Card.TFrame", padding=12); frm.pack(fill="both", expand=True); frm.columnconfigure(1, weight=1)
        cat = self.entry(frm); entry = tk.Text(frm, height=6, bg="#0b1220", fg=TEXT, insertbackground=TEXT, wrap="word")
        self.form_row(frm, "Category", cat, 0)
        ttk.Label(frm, text="Entry", background=CARD_BG).grid(row=1, column=0, sticky="nw", padx=4, pady=4)
        entry.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        def save():
            c = cat.get().strip() or "General"; e = entry.get("1.0","end").strip()
            if not e: return
            self.db.log(c, e); win.destroy(); self.refresh_all()
        ttk.Button(frm, text="Save Log Entry", style="Accent.TButton", command=save).grid(row=2, column=0, columnspan=2, pady=10)

    def document_window(self, doc_type):
        if not self.selected_job_id:
            messagebox.showinfo("Select", "Select a job first on the Jobs tab.")
            return
        j = self.db.one("SELECT j.*, COALESCE(c.name,'') customer, COALESCE(c.phone,'') cphone, COALESCE(c.address,'') caddr FROM jobs j LEFT JOIN customers c ON c.id=j.customer_id WHERE j.id=?", (self.selected_job_id,))
        win = tk.Toplevel(self); win.title(doc_type); win.geometry("760x700"); win.configure(bg=CARD_BG)
        frm = ttk.Frame(win, style="Card.TFrame", padding=12); frm.pack(fill="both", expand=True); frm.columnconfigure(1, weight=1)
        fields = {}
        base_price = j["contract_price"] or 0
        deposit = j["deposit_required"] or round(base_price/2, 2)
        values = {
            "title": f"{doc_type} - {j['job_name']}",
            "price": str(base_price),
            "deposit": str(deposit),
            "balance": str(base_price - deposit),
            "terms": DEFAULT_PAYMENT_TERMS,
            "exclusions": UNKNOWN_PROTECTION,
        }
        for i,k in enumerate(["title","price","deposit","balance"]):
            w = self.entry(frm); w.insert(0, values[k]); self.form_row(frm, k.title(), w, i); fields[k]=w
        scope = tk.Text(frm, height=12, bg="#0b1220", fg=TEXT, insertbackground=TEXT, wrap="word"); scope.insert("1.0", j["scope"] or "")
        terms = tk.Text(frm, height=4, bg="#0b1220", fg=TEXT, insertbackground=TEXT, wrap="word"); terms.insert("1.0", values["terms"])
        excl = tk.Text(frm, height=4, bg="#0b1220", fg=TEXT, insertbackground=TEXT, wrap="word"); excl.insert("1.0", values["exclusions"])
        for r, label, w in [(4,"Scope",scope),(5,"Payment Terms",terms),(6,"Notes/Exclusions",excl)]:
            ttk.Label(frm, text=label, background=CARD_BG).grid(row=r, column=0, sticky="nw", padx=4, pady=4)
            w.grid(row=r, column=1, sticky="ew", padx=4, pady=4)
        fields.update({"scope":scope,"terms":terms,"exclusions":excl})
        def save_and_make():
            title = fields["title"].get().strip()
            price = parse_money(fields["price"].get())
            deposit_val = parse_money(fields["deposit"].get())
            balance = parse_money(fields["balance"].get())
            scope_text = fields["scope"].get("1.0","end").strip()
            terms_text = fields["terms"].get("1.0","end").strip()
            excl_text = fields["exclusions"].get("1.0","end").strip()
            doc_no = f"{doc_type[:3].upper()}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
            file_path = self.generate_document_pdf(doc_type, doc_no, j, title, scope_text, price, deposit_val, balance, terms_text, excl_text)
            self.db.execute("INSERT INTO documents(job_id, doc_type, doc_number, date, title, scope, price, deposit, balance, terms, exclusions, file_path) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (j["id"], doc_type, doc_no, dt.date.today().isoformat(), title, scope_text, price, deposit_val, balance, terms_text, excl_text, str(file_path)))
            self.db.log("Document", f"Created {doc_type} {doc_no} for {j['job_name']}.")
            win.destroy(); self.refresh_all()
            messagebox.showinfo("Created", f"Created:\n{file_path}")
        ttk.Button(frm, text=f"Create {doc_type}", style="Accent.TButton", command=save_and_make).grid(row=7, column=0, columnspan=2, pady=10)

    def generate_document_pdf(self, doc_type, doc_no, job, title, scope, price, deposit, balance, terms, exclusions):
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in title)[:80]
        path = EXPORT_DIR / f"{safe}_{doc_no}.pdf"
        if REPORTLAB_OK:
            styles = getSampleStyleSheet()
            normal = ParagraphStyle('normal_dark', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=13)
            header = ParagraphStyle('header', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, textColor=colors.HexColor('#111827'))
            doc = SimpleDocTemplate(str(path), pagesize=letter, rightMargin=.6*inch, leftMargin=.6*inch, topMargin=.6*inch, bottomMargin=.6*inch)
            story = []
            story.append(Paragraph(f"{BUSINESS_NAME}", header))
            story.append(Paragraph(f"Phone: {PHONE} | Created: {now_stamp()}", normal))
            story.append(Spacer(1, .2*inch))
            story.append(Paragraph(f"<b>{doc_type.upper()}</b> &nbsp;&nbsp; {doc_no}", normal))
            story.append(Paragraph(f"<b>Customer:</b> {job['customer']}<br/><b>Job:</b> {job['job_name']}<br/><b>Address:</b> {job['job_address'] or job['caddr'] or ''}", normal))
            story.append(Spacer(1, .2*inch))
            story.append(Paragraph(f"<b>Scope of Work</b>", normal))
            for para in scope.split("\n"):
                if para.strip():
                    story.append(Paragraph(para.strip(), normal))
            story.append(Spacer(1, .2*inch))
            data = [["Total Price", money(price)], ["Deposit Due", money(deposit)], ["Balance Due", money(balance)]]
            table = Table(data, colWidths=[2.5*inch, 2*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#dcfce7')),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
                ('ALIGN', (1,0), (1,-1), 'RIGHT'),
                ('PADDING', (0,0), (-1,-1), 8),
            ]))
            story.append(table)
            story.append(Spacer(1, .2*inch))
            story.append(Paragraph(f"<b>Payment Terms</b><br/>{terms}", normal))
            story.append(Spacer(1, .1*inch))
            story.append(Paragraph(f"<b>Notes / Exclusions</b><br/>{exclusions}", normal))
            doc.build(story)
        else:
            path = EXPORT_DIR / f"{safe}_{doc_no}.html"
            path.write_text(f"""<html><body><h1>{BUSINESS_NAME}</h1><p>{PHONE} | {now_stamp()}</p><h2>{doc_type} {doc_no}</h2><p><b>Customer:</b> {job['customer']}<br><b>Job:</b> {job['job_name']}</p><h3>Scope</h3><pre>{scope}</pre><h3>Price</h3><p>Total: {money(price)}<br>Deposit: {money(deposit)}<br>Balance: {money(balance)}</p><h3>Terms</h3><p>{terms}</p><h3>Notes</h3><p>{exclusions}</p></body></html>""", encoding="utf-8")
        return path

    def export_query_csv(self, filename, sql, params=()):
        EXPORT_DIR.mkdir(exist_ok=True)
        path = EXPORT_DIR / filename
        rows = self.db.q(sql, params)
        with path.open("w", newline="", encoding="utf-8") as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=rows[0].keys())
                w.writeheader(); w.writerows([dict(r) for r in rows])
            else:
                f.write("No records\n")
        return path

    def export_expenses_csv(self):
        p = self.export_query_csv("JRC_Expenses_Export.csv", "SELECT * FROM expenses ORDER BY date DESC")
        messagebox.showinfo("Exported", str(p))

    def export_worker_1099_csv(self):
        p = self.export_query_csv("JRC_Worker_1099_Prep.csv", """
        SELECT w.name, w.w9_status, SUM(p.amount) AS total_paid, COUNT(*) AS payment_count
        FROM workers w LEFT JOIN worker_payments p ON p.worker_id=w.id AND p.status='Paid'
        GROUP BY w.id ORDER BY total_paid DESC
        """)
        messagebox.showinfo("Exported", str(p))

    def export_schedule_c_csv(self):
        path = EXPORT_DIR / "JRC_Schedule_C_Prep.csv"
        revenue = self.db.one("SELECT SUM(deposit_paid+balance_paid) AS total FROM jobs")["total"] or 0
        exp_rows = self.db.q("SELECT category, SUM(amount) AS total FROM expenses GROUP BY category")
        helper = self.db.one("SELECT SUM(amount) AS total FROM worker_payments WHERE status='Paid'")["total"] or 0
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Schedule C Area", "Amount", "Notes"])
            w.writerow(["Gross receipts / sales", revenue, "Confirmed money received in job records"])
            for r in exp_rows:
                w.writerow([r["category"], r["total"] or 0, "Expense log"])
            w.writerow(["Worker/Helper Pay", helper, "Worker payment ledger"])
            w.writerow(["Estimated Net Profit", revenue - sum((r["total"] or 0) for r in exp_rows) - helper, "Before other deductions"])
        messagebox.showinfo("Exported", str(path))

    def export_tax_files(self):
        self.export_schedule_c_csv()
        self.export_expenses_csv()
        self.export_worker_1099_csv()

    def export_all_reports(self):
        self.export_query_csv("JRC_Customers.csv", "SELECT * FROM customers ORDER BY name")
        self.export_query_csv("JRC_Jobs.csv", "SELECT * FROM jobs ORDER BY updated_at DESC")
        self.export_query_csv("JRC_Expenses.csv", "SELECT * FROM expenses ORDER BY date DESC")
        self.export_query_csv("JRC_Workers.csv", "SELECT * FROM workers ORDER BY name")
        self.export_query_csv("JRC_Worker_Payments.csv", "SELECT * FROM worker_payments ORDER BY date DESC")
        self.export_query_csv("JRC_Evidence_Index.csv", "SELECT * FROM evidence ORDER BY date DESC")
        self.export_query_csv("JRC_Business_Log.csv", "SELECT * FROM business_log ORDER BY id DESC")
        self.export_tax_files()
        if hasattr(self, "current_user") and self.current_user.get("role") == "Admin":
            self.export_user_index()
        messagebox.showinfo("Exported", f"Reports exported to:\n{EXPORT_DIR}")

    def make_backup(self):
        self.export_all_reports()
        stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        zip_path = EXPORT_DIR / f"JRC_Job_Manager_Backup_{stamp}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for p in [DB_PATH, BASE_DIR / "README.txt", BASE_DIR / "requirements.txt", Path(__file__).resolve()]:
                if p.exists(): z.write(p, p.relative_to(BASE_DIR))
            for folder in [EXPORT_DIR, EVIDENCE_DIR]:
                for p in folder.rglob("*"):
                    if p.is_file() and p != zip_path:
                        z.write(p, p.relative_to(BASE_DIR))
            manifest = f"J&R backup created {now_stamp()}\nDatabase: {DB_PATH}\n"
            z.writestr("BACKUP_MANIFEST.txt", manifest)
        self.db.log("Backup", f"Created backup ZIP {zip_path.name}.")
        self.refresh_all()
        messagebox.showinfo("Backup Created", str(zip_path))

    def open_exports(self):
        self.open_path(EXPORT_DIR)

    def open_path(self, path):
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                os.system(f"open '{path}'")
            else:
                os.system(f"xdg-open '{path}'")
        except Exception as e:
            messagebox.showerror("Open failed", str(e))


# ---------------- JRC_MANAGER_V21_EXTENSION ----------------
# Advanced install/update, session autosave, local Dropbox/ChatGPT file source indexing,
# and file explorer features. This section extends the original v1 app without removing
# existing business data or evidence.

SOURCE_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.txt', '.csv', '.xlsx', '.xls', '.docx', '.zip'}
TEXT_EXTENSIONS = {'.txt', '.csv', '.md', '.log'}
CHATGPT_IMPORTS_DIR = BASE_DIR / 'chatgpt_imports'
SESSION_PATH = DATA_DIR / 'current_session.json'
MAX_AUTO_SCAN_FILES = 1500

_orig_db_init_schema = Database.init_schema

def _v21_init_schema(self):
    _orig_db_init_schema(self)
    cur = self.conn.cursor()
    cur.executescript('''
        CREATE TABLE IF NOT EXISTS file_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL UNIQUE,
            source_type TEXT NOT NULL,
            root_path TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            last_scan TEXT,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS file_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL UNIQUE,
            relative_path TEXT,
            extension TEXT,
            size_bytes INTEGER DEFAULT 0,
            modified_at TEXT,
            file_hash TEXT,
            analysis_summary TEXT,
            indexed_at TEXT NOT NULL,
            FOREIGN KEY(source_id) REFERENCES file_sources(id)
        );
        CREATE TABLE IF NOT EXISTS source_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER,
            summary_key TEXT NOT NULL,
            summary_value TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(source_id, summary_key),
            FOREIGN KEY(source_id) REFERENCES file_sources(id)
        );
        CREATE TABLE IF NOT EXISTS app_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            device_id TEXT,
            started_at TEXT,
            saved_at TEXT,
            selected_tab TEXT,
            selected_job_id INTEGER,
            notes TEXT
        );
    ''')
    self.conn.commit()

_orig_db_seed_defaults = Database.seed_defaults

def _v21_seed_defaults(self):
    _orig_db_seed_defaults(self)
    CHATGPT_IMPORTS_DIR.mkdir(exist_ok=True)
    cur = self.conn.cursor()
    cur.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)", ('app_version', APP_VERSION))
    cur.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)", ('chatgpt_imports_folder', str(CHATGPT_IMPORTS_DIR)))
    cur.execute("INSERT OR IGNORE INTO file_sources(source_name, source_type, root_path, enabled, notes) VALUES(?,?,?,?,?)",
                ('ChatGPT Imports', 'ChatGPT', str(CHATGPT_IMPORTS_DIR), 1, 'Drop files exported or downloaded from ChatGPT here for local analysis.'))
    dropbox_folder = self.get_setting('dropbox_folder', '')
    if dropbox_folder:
        cur.execute("INSERT OR IGNORE INTO file_sources(source_name, source_type, root_path, enabled, notes) VALUES(?,?,?,?,?)",
                    ('Dropbox Business Folder', 'DropboxLocal', dropbox_folder, 1, 'Local Dropbox-synced business folder.'))
    self.conn.commit()

Database.init_schema = _v21_init_schema
Database.seed_defaults = _v21_seed_defaults


def _sha256_file(path: Path, limit_bytes=None):
    import hashlib
    h = hashlib.sha256()
    total = 0
    with path.open('rb') as f:
        while True:
            chunk = f.read(1024*1024)
            if not chunk:
                break
            h.update(chunk)
            total += len(chunk)
            if limit_bytes and total >= limit_bytes:
                break
    return h.hexdigest()


def _analyze_file(path: Path):
    ext = path.suffix.lower()
    name = path.name.lower()
    pieces = []
    if ext:
        pieces.append(ext.replace('.', '').upper() + ' file')
    if any(k in name for k in ['tax', 'schedule', '1099', 'w9', 'payroll']):
        pieces.append('tax/payroll related')
    if any(k in name for k in ['invoice', 'estimate', 'scope']):
        pieces.append('customer document')
    if any(k in name for k in ['receipt', 'lowe', 'billing', 'ticket']):
        pieces.append('receipt/evidence likely')
    if ext in TEXT_EXTENSIONS:
        try:
            txt = path.read_text(encoding='utf-8', errors='ignore')[:5000]
            lowered = txt.lower()
            found=[]
            for word in ['paid','deposit','balance','cash','check','worker','helper','materials','insurance','vehicle','truck','schedule c']:
                if word in lowered:
                    found.append(word)
            if found:
                pieces.append('keywords: ' + ', '.join(found[:10]))
        except Exception:
            pass
    return '; '.join(pieces) if pieces else 'indexed file'


def _safe_rel(path: Path, root: Path):
    try:
        return str(path.relative_to(root))
    except Exception:
        return path.name


def _scan_source_to_db(db: Database, source_row, max_files=MAX_AUTO_SCAN_FILES):
    root = Path(source_row['root_path'])
    if not root.exists():
        db.execute("INSERT OR REPLACE INTO source_summaries(source_id,summary_key,summary_value,updated_at) VALUES(?,?,?,?)", (source_row['id'], 'status', 'Missing path', iso_now()))
        return {'count':0, 'status':'missing'}
    count = 0
    changed = 0
    for p in root.rglob('*'):
        if count >= max_files:
            break
        if not p.is_file():
            continue
        if p.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        count += 1
        try:
            stat = p.stat()
            mod = dt.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds')
            size = stat.st_size
            old = db.one("SELECT size_bytes, modified_at, file_hash FROM file_index WHERE file_path=?", (str(p),))
            if old and old['size_bytes'] == size and old['modified_at'] == mod:
                continue
            digest = _sha256_file(p, limit_bytes=50*1024*1024)
            summary = _analyze_file(p)
            db.execute('''INSERT INTO file_index(source_id,file_name,file_path,relative_path,extension,size_bytes,modified_at,file_hash,analysis_summary,indexed_at)
                          VALUES(?,?,?,?,?,?,?,?,?,?)
                          ON CONFLICT(file_path) DO UPDATE SET source_id=excluded.source_id,file_name=excluded.file_name,relative_path=excluded.relative_path,extension=excluded.extension,size_bytes=excluded.size_bytes,modified_at=excluded.modified_at,file_hash=excluded.file_hash,analysis_summary=excluded.analysis_summary,indexed_at=excluded.indexed_at''',
                       (source_row['id'], p.name, str(p), _safe_rel(p, root), p.suffix.lower(), size, mod, digest, summary, iso_now()))
            changed += 1
        except Exception as e:
            db.log('File Source Error', f'Could not index {p}: {e}')
    db.execute("UPDATE file_sources SET last_scan=? WHERE id=?", (iso_now(), source_row['id']))
    db.execute("INSERT OR REPLACE INTO source_summaries(source_id,summary_key,summary_value,updated_at) VALUES(?,?,?,?)", (source_row['id'], 'last_file_count', str(count), iso_now()))
    db.execute("INSERT OR REPLACE INTO source_summaries(source_id,summary_key,summary_value,updated_at) VALUES(?,?,?,?)", (source_row['id'], 'last_changed_count', str(changed), iso_now()))
    return {'count': count, 'changed': changed, 'status':'ok'}


def _import_known_tax_files(db: Database):
    # Read latest indexed JRC_Tax CSVs into source summaries so dashboard reflects source files.
    # This does not overwrite job records; it displays source totals separately for review.
    import csv as _csv
    totals = {'source_paid_income':0.0, 'source_pending_income':0.0, 'source_materials':0.0, 'source_workers':0.0}
    rows = db.q("SELECT file_path, file_name FROM file_index WHERE lower(file_name) LIKE 'jrc_tax_%2026.csv' OR lower(file_name) LIKE 'jrc_tax_%payments_2026.csv'")
    for r in rows:
        p = Path(r['file_path'])
        if not p.exists():
            continue
        lname = r['file_name'].lower()
        try:
            with p.open(newline='', encoding='utf-8-sig', errors='ignore') as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    if 'income_by_job' in lname:
                        amt = parse_money(row.get('Amount') or row.get('amount') or 0)
                        status = (row.get('Status') or '').lower()
                        if 'paid' in status and 'pending' not in status:
                            totals['source_paid_income'] += amt
                        else:
                            totals['source_pending_income'] += amt
                    elif 'materials' in lname:
                        totals['source_materials'] += parse_money(row.get('Amount') or row.get('amount') or 0)
                    elif 'worker' in lname or 'payments' in lname:
                        totals['source_workers'] += parse_money(row.get('Amount Paid') or row.get('amount paid') or row.get('Amount') or 0)
        except Exception as e:
            db.log('Source Import', f'Could not summarize {p.name}: {e}')
    for k,v in totals.items():
        db.execute("INSERT OR REPLACE INTO source_summaries(source_id,summary_key,summary_value,updated_at) VALUES(?,?,?,?)", (0, k, str(round(v,2)), iso_now()))
    return totals


def _open_selected_file(app):
    if not hasattr(app, 'files_tree'):
        return
    sel = app.files_tree.selection()
    if not sel:
        messagebox.showwarning('Select file', 'Select a file first.')
        return
    vals = app.files_tree.item(sel[0], 'values')
    path = vals[5] if len(vals) > 5 else ''
    if path:
        app.open_path(Path(path))


def _reveal_selected_file(app):
    sel = app.files_tree.selection() if hasattr(app, 'files_tree') else []
    if not sel:
        messagebox.showwarning('Select file', 'Select a file first.')
        return
    vals = app.files_tree.item(sel[0], 'values')
    path = Path(vals[5])
    app.open_path(path.parent)


def _copy_selected_to_evidence(app):
    sel = app.files_tree.selection() if hasattr(app, 'files_tree') else []
    if not sel:
        messagebox.showwarning('Select file', 'Select a file first.')
        return
    vals = app.files_tree.item(sel[0], 'values')
    src = Path(vals[5])
    if not src.exists():
        messagebox.showerror('Missing file', 'The selected file does not exist on this PC.')
        return
    EVIDENCE_DIR.mkdir(exist_ok=True)
    dest = EVIDENCE_DIR / src.name
    if dest.exists():
        dest = EVIDENCE_DIR / f"{src.stem}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}{src.suffix}"
    shutil.copy2(src, dest)
    app.db.execute("INSERT INTO evidence(date,file_name,file_path,evidence_type,description,notes) VALUES(?,?,?,?,?,?)", (dt.date.today().isoformat(), dest.name, str(dest), 'Imported File', 'Copied from File Explorer', str(src)))
    app.db.log('Evidence', f'Copied source file into evidence folder: {dest.name}')
    app.refresh_all()
    messagebox.showinfo('Copied', f'Copied into evidence folder:\n{dest}')


def _save_session(app):
    try:
        tab = app.nb.tab(app.nb.select(), 'text') if hasattr(app, 'nb') else ''
        data = {
            'username': app.current_user.get('username','') if hasattr(app,'current_user') else '',
            'device_id': get_device_id(),
            'saved_at': iso_now(),
            'selected_tab': tab,
            'selected_job_id': getattr(app, 'selected_job_id', None),
            'app_version': APP_VERSION,
        }
        DATA_DIR.mkdir(exist_ok=True)
        SESSION_PATH.write_text(json.dumps(data, indent=2), encoding='utf-8')
        app.db.execute("INSERT INTO app_sessions(username,device_id,started_at,saved_at,selected_tab,selected_job_id,notes) VALUES(?,?,?,?,?,?,?)", (data['username'], data['device_id'], data.get('started_at', iso_now()), data['saved_at'], tab, data['selected_job_id'], 'Auto-saved session'))
    except Exception as e:
        try: app.db.log('Session Error', str(e))
        except Exception: pass


def _autosave_loop(app):
    _save_session(app)
    app.after(120000, lambda: _autosave_loop(app))


def _on_close(app):
    _save_session(app)
    app.db.log('Session', 'Program closed; session auto-saved.')
    app.destroy()

_orig_app_init = DarkApp.__init__
def _v21_app_init(self):
    _orig_app_init(self)
    self.protocol('WM_DELETE_WINDOW', lambda: _on_close(self))
    self.db.log('System', f'Opened {APP_NAME} version {APP_VERSION}; session auto-save enabled.')
    self.after(3000, lambda: _autosave_loop(self))

DarkApp.__init__ = _v21_app_init

_orig_build_layout = DarkApp.build_layout

def _v21_build_layout(self):
    _orig_build_layout(self)
    # Add after original tabs so existing workflow stays familiar.
    self.files_tab = ttk.Frame(self.nb)
    self.nb.add(self.files_tab, text='File Explorer')
    self.build_file_explorer()

DarkApp.build_layout = _v21_build_layout


def _build_file_explorer(self):
    wrap = ttk.Frame(self.files_tab)
    wrap.pack(fill='both', expand=True, padx=8, pady=8)
    top = self.card(wrap, 'Business File Explorer and Source Analyzer')
    top.pack(fill='x', padx=4, pady=4)
    info = ('Scans local Dropbox-synced folders, program evidence, exports, and ChatGPT import files. '
            'Refresh updates the index so you can see the most current files available on this PC. '
            'The program does not expose your files to the public internet.')
    ttk.Label(top, text=info, background=CARD_BG, foreground=TEXT, wraplength=1100).pack(anchor='w', pady=(4,8))
    row = ttk.Frame(top, style='Card.TFrame')
    row.pack(fill='x')
    ttk.Label(row, text='Search:', background=CARD_BG).pack(side='left', padx=4)
    self.file_search_var = tk.StringVar()
    ttk.Entry(row, textvariable=self.file_search_var, width=45).pack(side='left', padx=4)
    ttk.Button(row, text='Search/Filter', command=self.refresh_file_explorer).pack(side='left', padx=3)
    ttk.Button(row, text='Scan Sources Now', style='Accent.TButton', command=self.scan_sources_now).pack(side='left', padx=3)
    ttk.Button(row, text='Open File', command=lambda: _open_selected_file(self)).pack(side='left', padx=3)
    ttk.Button(row, text='Open Folder', command=lambda: _reveal_selected_file(self)).pack(side='left', padx=3)
    ttk.Button(row, text='Copy to Evidence', command=lambda: _copy_selected_to_evidence(self)).pack(side='left', padx=3)

    mid = ttk.Frame(wrap)
    mid.pack(fill='both', expand=True, padx=4, pady=4)
    left = self.card(mid, 'File Sources')
    left.pack(side='left', fill='y', padx=(0,6))
    b = ttk.Frame(left, style='Card.TFrame'); b.pack(fill='x')
    ttk.Button(b, text='Add Source', command=self.add_file_source_window).pack(side='left', padx=3)
    ttk.Button(b, text='Toggle Source', command=self.toggle_file_source).pack(side='left', padx=3)
    self.sources_tree = self.make_tree(left, ['ID','Name','Type','Enabled','Last Scan'], height=18)
    right = self.card(mid, 'Indexed Files')
    right.pack(side='left', fill='both', expand=True)
    self.files_tree = self.make_tree(right, ['ID','Source','File','Type','Modified','Path','Analysis'], height=22)
    self.files_tree.column('Path', width=360)
    self.files_tree.column('Analysis', width=300)

DarkApp.build_file_explorer = _build_file_explorer


def _refresh_file_sources(self):
    if not hasattr(self, 'sources_tree'):
        return
    self.clear_tree(self.sources_tree)
    for r in self.db.q('SELECT * FROM file_sources ORDER BY source_name'):
        self.sources_tree.insert('', 'end', values=[r['id'], r['source_name'], r['source_type'], 'Yes' if r['enabled'] else 'No', r['last_scan'] or ''])


def _refresh_file_explorer(self):
    if not hasattr(self, 'files_tree'):
        return
    self.clear_tree(self.files_tree)
    term = self.file_search_var.get().strip().lower() if hasattr(self, 'file_search_var') else ''
    sql = '''SELECT fi.*, fs.source_name FROM file_index fi LEFT JOIN file_sources fs ON fs.id=fi.source_id ORDER BY fi.modified_at DESC, fi.file_name LIMIT 1000'''
    for r in self.db.q(sql):
        blob = ' '.join(str(r[k] or '') for k in ['file_name','relative_path','extension','analysis_summary']).lower()
        if term and term not in blob:
            continue
        self.files_tree.insert('', 'end', values=[r['id'], r['source_name'] or 'Internal', r['file_name'], r['extension'], r['modified_at'] or '', r['file_path'], r['analysis_summary'] or ''])

DarkApp.refresh_file_sources = _refresh_file_sources
DarkApp.refresh_file_explorer = _refresh_file_explorer


def _scan_sources_now(self, quiet=False):
    # Make sure current Dropbox setting is mirrored as a file source.
    dropbox_folder = self.db.get_setting('dropbox_folder','')
    if dropbox_folder:
        self.db.execute("INSERT INTO file_sources(source_name,source_type,root_path,enabled,notes) VALUES(?,?,?,?,?) ON CONFLICT(source_name) DO UPDATE SET root_path=excluded.root_path, enabled=1", ('Dropbox Business Folder','DropboxLocal',dropbox_folder,1,'Local Dropbox-synced business folder.'))
    self.db.execute("INSERT INTO file_sources(source_name,source_type,root_path,enabled,notes) VALUES(?,?,?,?,?) ON CONFLICT(source_name) DO UPDATE SET root_path=excluded.root_path, enabled=1", ('Program Evidence','LocalEvidence',str(EVIDENCE_DIR),1,'Program evidence folder.'))
    self.db.execute("INSERT INTO file_sources(source_name,source_type,root_path,enabled,notes) VALUES(?,?,?,?,?) ON CONFLICT(source_name) DO UPDATE SET root_path=excluded.root_path, enabled=1", ('Program Exports','LocalExports',str(EXPORT_DIR),1,'Program export folder.'))
    total = 0; changed = 0; messages=[]
    for s in self.db.q('SELECT * FROM file_sources WHERE enabled=1'):
        res = _scan_source_to_db(self.db, s)
        total += res.get('count',0); changed += res.get('changed',0)
        messages.append(f"{s['source_name']}: {res.get('count',0)} files, {res.get('changed',0)} updated")
    totals = _import_known_tax_files(self.db)
    self.db.log('File Sources', f'Scanned sources: {total} files checked, {changed} changed. Source totals: {totals}')
    self.refresh_file_sources(); self.refresh_file_explorer(); self.refresh_dashboard(); self.refresh_log()
    if not quiet:
        messagebox.showinfo('Source Scan Complete', '\n'.join(messages) + f"\n\nSource totals refreshed from known JRC tax CSVs.")

DarkApp.scan_sources_now = _scan_sources_now


def _add_file_source_window(self):
    win = tk.Toplevel(self); win.title('Add File Source'); win.configure(bg=DARK_BG)
    f = ttk.Frame(win, style='Card.TFrame', padding=14); f.pack(fill='both', expand=True, padx=10, pady=10)
    vals={}
    for i,label in enumerate(['Source Name','Source Type']):
        ttk.Label(f, text=label, background=CARD_BG).grid(row=i, column=0, sticky='w', padx=4, pady=4)
        e=ttk.Entry(f, width=45); e.grid(row=i, column=1, sticky='ew', padx=4, pady=4); vals[label]=e
    vals['Source Type'].insert(0,'LocalFolder')
    ttk.Label(f, text='Folder', background=CARD_BG).grid(row=2, column=0, sticky='w', padx=4, pady=4)
    folder_var=tk.StringVar(); ttk.Entry(f, textvariable=folder_var, width=55).grid(row=2, column=1, sticky='ew', padx=4, pady=4)
    ttk.Button(f, text='Browse', command=lambda: folder_var.set(filedialog.askdirectory(title='Choose source folder') or folder_var.get())).grid(row=2,column=2,padx=4)
    def save():
        name=vals['Source Name'].get().strip(); typ=vals['Source Type'].get().strip() or 'LocalFolder'; root=folder_var.get().strip()
        if not name or not root:
            messagebox.showerror('Missing','Source name and folder are required.'); return
        self.db.execute("INSERT INTO file_sources(source_name,source_type,root_path,enabled,notes) VALUES(?,?,?,?,?) ON CONFLICT(source_name) DO UPDATE SET source_type=excluded.source_type, root_path=excluded.root_path, enabled=1", (name,typ,root,1,'Added by admin'))
        self.db.log('File Sources', f'Added/updated file source: {name} -> {root}')
        win.destroy(); self.scan_sources_now(quiet=True)
    ttk.Button(f, text='Save Source', style='Accent.TButton', command=save).grid(row=3,column=1,sticky='e',pady=8)

DarkApp.add_file_source_window = _add_file_source_window


def _toggle_file_source(self):
    sel = self.sources_tree.selection() if hasattr(self,'sources_tree') else []
    if not sel:
        messagebox.showwarning('Select source','Select a source first.'); return
    sid = int(self.sources_tree.item(sel[0],'values')[0])
    row = self.db.one('SELECT enabled, source_name FROM file_sources WHERE id=?',(sid,))
    if row:
        new = 0 if row['enabled'] else 1
        self.db.execute('UPDATE file_sources SET enabled=? WHERE id=?',(new,sid))
        self.db.log('File Sources', f"{'Enabled' if new else 'Disabled'} source {row['source_name']}")
        self.refresh_file_sources()

DarkApp.toggle_file_source = _toggle_file_source

_orig_refresh_all = DarkApp.refresh_all

def _v21_refresh_all(self):
    _orig_refresh_all(self)
    try:
        # Quiet scan on refresh so file explorer reflects sources. Limit prevents runaway scans.
        self.scan_sources_now(quiet=True)
    except Exception as e:
        self.db.log('File Source Error', f'Refresh scan failed: {e}')
    try:
        _save_session(self)
    except Exception:
        pass

DarkApp.refresh_all = _v21_refresh_all

_orig_refresh_dashboard = DarkApp.refresh_dashboard

def _v21_refresh_dashboard(self):
    _orig_refresh_dashboard(self)
    try:
        src_paid = self.db.one("SELECT summary_value FROM source_summaries WHERE source_id=0 AND summary_key='source_paid_income'")
        src_mat = self.db.one("SELECT summary_value FROM source_summaries WHERE source_id=0 AND summary_key='source_materials'")
        src_workers = self.db.one("SELECT summary_value FROM source_summaries WHERE source_id=0 AND summary_key='source_workers'")
        if src_paid and hasattr(self, 'alert_text'):
            self.alert_text.insert('end', '\nSOURCE FILE TOTALS FROM LATEST SCAN\n')
            self.alert_text.insert('end', f"Paid income from source CSVs: {money(src_paid['summary_value'])}\n")
            self.alert_text.insert('end', f"Materials from source CSVs: {money(src_mat['summary_value'] if src_mat else 0)}\n")
            self.alert_text.insert('end', f"Worker payments from source CSVs: {money(src_workers['summary_value'] if src_workers else 0)}\n")
    except Exception:
        pass

DarkApp.refresh_dashboard = _v21_refresh_dashboard

_orig_save_dropbox_folder = DarkApp.save_dropbox_folder

def _v21_save_dropbox_folder(self):
    _orig_save_dropbox_folder(self)
    folder = self.dropbox_path_var.get().strip()
    if folder:
        self.db.execute("INSERT INTO file_sources(source_name,source_type,root_path,enabled,notes) VALUES(?,?,?,?,?) ON CONFLICT(source_name) DO UPDATE SET root_path=excluded.root_path, enabled=1", ('Dropbox Business Folder','DropboxLocal',folder,1,'Local Dropbox-synced business folder.'))
        self.scan_sources_now(quiet=True)

DarkApp.save_dropbox_folder = _v21_save_dropbox_folder

_orig_make_backup = DarkApp.make_backup

def _v21_make_backup(self):
    _save_session(self)
    _orig_make_backup(self)

DarkApp.make_backup = _v21_make_backup
# ---------------- END JRC_MANAGER_V21_EXTENSION ----------------


# ---------------- JRC_MANAGER_V25_BUSINESS_STANDARDS_EXTENSION ----------------
BUSINESS_STANDARD_DEFINITIONS = [
    ('business_name', 'Business name on documents', 'J & R Construction'),
    ('business_phone', 'Business phone on documents', '(910) 712-0936'),
    ('business_owner', 'Owner/operator', 'Jacob Cosentino'),
    ('document_datetime', 'Show current date/time on every document', 'Yes'),
    ('include_address', 'Include business address on customer documents', 'No'),
    ('business_address', 'Business address if enabled', ''),
    ('include_email', 'Include business email on customer documents', 'No'),
    ('business_email', 'Business email if enabled', ''),
    ('include_license', 'Include license number on customer documents', 'No'),
    ('business_license', 'License number if enabled', ''),
    ('default_payment_terms', 'Default payment terms', '50% deposit due before work begins. Remaining 50% balance due upon completion.'),
    ('unknown_conditions_clause', 'Unknown-condition protection clause', 'Price may change if hidden damage, rot, structural issues, code issues, unsafe conditions, or additional required work is discovered after opening up the work area.'),
    ('painting_addon_rule', 'Painting/add-on rule', 'Painting and optional add-ons must be listed separately and excluded from the main price unless specifically included.'),
    ('customer_internal_rule', 'Customer/internal separation rule', 'Customer-facing documents must not include internal cost sheets, helper cost notes, profit notes, or tax-only notes.'),
    ('internal_watermark', 'Internal document watermark', 'INTERNAL USE ONLY - NOT CUSTOMER COPY'),
    ('signature_lines', 'Add signature/date lines by default', 'No'),
    ('document_default_format', 'Default document format', 'PDF when reportlab is installed; HTML fallback if PDF engine is unavailable.'),
    ('estimate_prefix', 'Estimate number prefix', 'EST'),
    ('invoice_prefix', 'Invoice number prefix', 'INV'),
    ('log_timestamp_rule', 'Log timestamp rule', 'Every business log, payment note, file note, tax/admin update, and customer communication should include date and time.'),
    ('owner_labor_rule', 'Owner labor tax rule', 'Owner labor is job-costing only for a sole proprietor and is not a deductible wage paid to the owner.'),
    ('cash_income_rule', 'Cash income rule', 'Cash payments are business income when received even if no 1099/customer tax report is expected.'),
    ('receipt_rule', 'Receipt/evidence rule', 'Keep receipt photos, PDFs, screenshots, invoices, payment notes, and final balance notes with the job record.'),
    ('closeout_rule', 'Closeout checklist standard', 'Each job should have estimate or invoice PDF, internal job cost sheet, receipt evidence, helper payment notes, final paid/unpaid balance note, and final photos where applicable.'),
    ('file_naming_rule', 'File naming standard', 'Use JRC_ prefix or clear customer/job/date names. Avoid unclear temp names for final records.'),
]

STANDARDS_DIR = BASE_DIR / 'business_standards'
TEMPLATES_DIR = BASE_DIR / 'document_templates'

def _std_key(key):
    return 'std_' + key

def _ensure_business_standards(db):
    STANDARDS_DIR.mkdir(exist_ok=True)
    TEMPLATES_DIR.mkdir(exist_ok=True)
    for key, label, value in BUSINESS_STANDARD_DEFINITIONS:
        cur = db.one('SELECT value FROM app_settings WHERE key=?', (_std_key(key),))
        if cur is None:
            db.set_setting(_std_key(key), value)
    standards = {key: db.get_setting(_std_key(key), default) for key, label, default in BUSINESS_STANDARD_DEFINITIONS}
    standards['generated_at'] = now_stamp()
    standards['program'] = APP_NAME
    standards['program_version'] = APP_VERSION
    (STANDARDS_DIR / 'JRC_Business_Document_Standards.json').write_text(json.dumps(standards, indent=2), encoding='utf-8')
    with (STANDARDS_DIR / 'JRC_Business_Document_Standards.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Key','Label','Value'])
        for key, label, default in BUSINESS_STANDARD_DEFINITIONS:
            w.writerow([key, label, standards.get(key, default)])
    (TEMPLATES_DIR / 'JRC_Customer_Estimate_Template.txt').write_text('J & R Construction customer estimate template. Uses branded header, phone, timestamp, scope, price, 50/50 terms, unknown-condition clause, no internal notes.\n', encoding='utf-8')
    (TEMPLATES_DIR / 'JRC_Customer_Invoice_Template.txt').write_text('J & R Construction customer invoice template. Uses branded header, phone, timestamp, payment terms, balance, no internal cost details.\n', encoding='utf-8')
    (TEMPLATES_DIR / 'JRC_Internal_Cost_Sheet_Template.txt').write_text('Internal cost sheet template. Mark as INTERNAL USE ONLY and keep separate from customer-facing documents.\n', encoding='utf-8')

_prev_seed_defaults_v25 = Database.seed_defaults

def _v25_seed_defaults(self):
    _prev_seed_defaults_v25(self)
    _ensure_business_standards(self)
    self.set_setting('app_version', APP_VERSION)

Database.seed_defaults = _v25_seed_defaults

def _get_standard(db, key, fallback=''):
    return db.get_setting(_std_key(key), fallback)

def _is_yes(value):
    return str(value).strip().lower() in ('yes','true','1','y','on')

def _standards_snapshot(db):
    return {key: _get_standard(db, key, default) for key, label, default in BUSINESS_STANDARD_DEFINITIONS}

def _build_standards(self):
    _ensure_business_standards(self.db)
    wrap = ttk.Frame(self.standards_tab)
    wrap.pack(fill='both', expand=True, padx=8, pady=8)
    top = self.card(wrap, 'J&R Business Standards - Editable Controls')
    top.pack(fill='x', padx=4, pady=4)
    info = ('These settings drive customer PDFs/HTML fallbacks, tax exports, file naming, evidence handling, and job closeout rules. Change them here any time. The program saves them in the database and exports JSON/CSV copies for audit backup.')
    ttk.Label(top, text=info, background=CARD_BG, foreground=TEXT, wraplength=1120).pack(anchor='w', pady=(4,8))
    btn = ttk.Frame(top, style='Card.TFrame'); btn.pack(fill='x')
    ttk.Button(btn, text='Edit Selected Standard', style='Accent.TButton', command=lambda: _edit_selected_standard(self)).pack(side='left', padx=3)
    ttk.Button(btn, text='Export Standards JSON/CSV', command=lambda: _export_standards_files(self)).pack(side='left', padx=3)
    ttk.Button(btn, text='Reset Missing Defaults', command=lambda: _reset_missing_standards(self)).pack(side='left', padx=3)
    ttk.Button(btn, text='Open Standards Folder', command=lambda: self.open_path(STANDARDS_DIR)).pack(side='left', padx=3)
    mid = self.card(wrap, 'Active Business Standards')
    mid.pack(fill='both', expand=True, padx=4, pady=4)
    self.standards_tree = self.make_tree(mid, ['Key','Standard','Value'], height=25)
    self.standards_tree.column('Key', width=180)
    self.standards_tree.column('Standard', width=320)
    self.standards_tree.column('Value', width=650)
    self.refresh_standards()

DarkApp.build_standards = _build_standards

def _refresh_standards(self):
    if not hasattr(self, 'standards_tree'):
        return
    self.standards_tree.delete(*self.standards_tree.get_children())
    for key, label, default in BUSINESS_STANDARD_DEFINITIONS:
        self.standards_tree.insert('', 'end', values=[key, label, _get_standard(self.db, key, default)])

DarkApp.refresh_standards = _refresh_standards

def _edit_selected_standard(self):
    sel = self.standards_tree.selection() if hasattr(self, 'standards_tree') else []
    if not sel:
        messagebox.showinfo('Select', 'Select a standard first.')
        return
    vals = self.standards_tree.item(sel[0], 'values')
    key, label, current = vals[0], vals[1], vals[2]
    win = tk.Toplevel(self); win.title('Edit Business Standard'); win.configure(bg=CARD_BG); win.geometry('780x360')
    frm = ttk.Frame(win, style='Card.TFrame', padding=12); frm.pack(fill='both', expand=True)
    ttk.Label(frm, text=label, style='CardHeader.TLabel').pack(anchor='w')
    ttk.Label(frm, text=f'Key: {key}', background=CARD_BG, foreground=MUTED).pack(anchor='w', pady=(2,8))
    text = tk.Text(frm, height=8, bg='#0b1220', fg=TEXT, insertbackground=TEXT, wrap='word', relief='flat')
    text.pack(fill='both', expand=True); text.insert('1.0', current)
    def save():
        value = text.get('1.0','end').strip()
        self.db.set_setting(_std_key(key), value)
        _ensure_business_standards(self.db)
        self.db.log('Business Standards', f'Updated standard {key}.')
        win.destroy(); self.refresh_standards(); self.refresh_log()
    ttk.Button(frm, text='Save Standard', style='Accent.TButton', command=save).pack(anchor='e', pady=10)

def _export_standards_files(self):
    _ensure_business_standards(self.db)
    self.db.log('Business Standards', 'Exported business standards JSON and CSV.')
    self.refresh_log()
    messagebox.showinfo('Exported', f'Standards exported to:\n{STANDARDS_DIR}')

def _reset_missing_standards(self):
    _ensure_business_standards(self.db)
    self.refresh_standards()
    messagebox.showinfo('Checked', 'Missing business standard defaults have been restored. Existing customized values were preserved.')

_prev_build_layout_v25 = DarkApp.build_layout

def _v25_build_layout(self):
    _prev_build_layout_v25(self)
    self.standards_tab = ttk.Frame(self.nb)
    self.nb.add(self.standards_tab, text='Standards')
    self.build_standards()

DarkApp.build_layout = _v25_build_layout

_prev_refresh_all_v25 = DarkApp.refresh_all

def _v25_refresh_all(self):
    _prev_refresh_all_v25(self)
    try:
        _ensure_business_standards(self.db)
        self.refresh_standards()
    except Exception as e:
        try: self.db.log('Standards Error', str(e))
        except Exception: pass

DarkApp.refresh_all = _v25_refresh_all

def _v25_document_window(self, doc_type):
    if not self.selected_job_id:
        messagebox.showinfo('Select', 'Select a job first on the Jobs tab.')
        return
    j = self.db.one("SELECT j.*, COALESCE(c.name,'') customer, COALESCE(c.phone,'') cphone, COALESCE(c.address,'') caddr FROM jobs j LEFT JOIN customers c ON c.id=j.customer_id WHERE j.id=?", (self.selected_job_id,))
    standards = _standards_snapshot(self.db)
    win = tk.Toplevel(self); win.title(doc_type); win.geometry('800x740'); win.configure(bg=CARD_BG)
    frm = ttk.Frame(win, style='Card.TFrame', padding=12); frm.pack(fill='both', expand=True); frm.columnconfigure(1, weight=1)
    fields = {}
    base_price = j['contract_price'] or 0
    deposit = j['deposit_required'] or round(base_price / 2, 2)
    prefix = standards.get('invoice_prefix','INV') if doc_type.lower().startswith('invoice') else standards.get('estimate_prefix','EST')
    values = {
        'title': f"{doc_type} - {j['job_name']}",
        'price': str(base_price),
        'deposit': str(deposit),
        'balance': str(base_price - deposit),
        'terms': standards.get('default_payment_terms', DEFAULT_PAYMENT_TERMS),
        'exclusions': standards.get('unknown_conditions_clause', UNKNOWN_PROTECTION) + '\n' + standards.get('painting_addon_rule',''),
    }
    for i, k in enumerate(['title','price','deposit','balance']):
        w = self.entry(frm); w.insert(0, values[k]); self.form_row(frm, k.title(), w, i); fields[k] = w
    scope = tk.Text(frm, height=12, bg='#0b1220', fg=TEXT, insertbackground=TEXT, wrap='word'); scope.insert('1.0', j['scope'] or '')
    terms = tk.Text(frm, height=4, bg='#0b1220', fg=TEXT, insertbackground=TEXT, wrap='word'); terms.insert('1.0', values['terms'])
    excl = tk.Text(frm, height=5, bg='#0b1220', fg=TEXT, insertbackground=TEXT, wrap='word'); excl.insert('1.0', values['exclusions'])
    standards_note = tk.Text(frm, height=4, bg='#0b1220', fg=TEXT, insertbackground=TEXT, wrap='word')
    standards_note.insert('1.0', 'Document will use active J&R standards: branded header, phone, current timestamp, 50/50 terms unless changed, no business address/email/license unless enabled, and no signature/date lines unless enabled.')
    for r, label, w in [(4,'Scope',scope),(5,'Payment Terms',terms),(6,'Notes/Exclusions',excl),(7,'Standards Check',standards_note)]:
        ttk.Label(frm, text=label, background=CARD_BG).grid(row=r, column=0, sticky='nw', padx=4, pady=4)
        w.grid(row=r, column=1, sticky='ew', padx=4, pady=4)
    standards_note.config(state='disabled')
    fields.update({'scope': scope, 'terms': terms, 'exclusions': excl})
    def save_and_make():
        title = fields['title'].get().strip()
        price = parse_money(fields['price'].get())
        deposit_val = parse_money(fields['deposit'].get())
        balance = parse_money(fields['balance'].get())
        scope_text = fields['scope'].get('1.0','end').strip()
        terms_text = fields['terms'].get('1.0','end').strip()
        excl_text = fields['exclusions'].get('1.0','end').strip()
        doc_no = f"{prefix}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        file_path = self.generate_document_pdf(doc_type, doc_no, j, title, scope_text, price, deposit_val, balance, terms_text, excl_text)
        self.db.execute('INSERT INTO documents(job_id, doc_type, doc_number, date, title, scope, price, deposit, balance, terms, exclusions, file_path) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (j['id'], doc_type, doc_no, dt.date.today().isoformat(), title, scope_text, price, deposit_val, balance, terms_text, excl_text, str(file_path)))
        self.db.log('Document', f'Created standards-controlled {doc_type} {doc_no} for {j["job_name"]}.')
        win.destroy(); self.refresh_all()
        messagebox.showinfo('Created', f'Created:\n{file_path}')
    ttk.Button(frm, text=f'Create Standards-Controlled {doc_type}', style='Accent.TButton', command=save_and_make).grid(row=8, column=0, columnspan=2, pady=10)

DarkApp.document_window = _v25_document_window

def _v25_generate_document_pdf(self, doc_type, doc_no, job, title, scope, price, deposit, balance, terms, exclusions):
    _ensure_business_standards(self.db)
    std = _standards_snapshot(self.db)
    safe = safe_filename(f'{title}_{doc_no}')[:95]
    path = EXPORT_DIR / f'{safe}.pdf'
    business = std.get('business_name', BUSINESS_NAME)
    phone = std.get('business_phone', PHONE)
    owner = std.get('business_owner', 'Jacob Cosentino')
    show_sig = _is_yes(std.get('signature_lines','No'))
    meta_bits = [f'Phone: {phone}']
    if _is_yes(std.get('document_datetime','Yes')):
        meta_bits.append(f'Created: {now_stamp()}')
    if _is_yes(std.get('include_address','No')) and std.get('business_address'):
        meta_bits.append(std.get('business_address'))
    if _is_yes(std.get('include_email','No')) and std.get('business_email'):
        meta_bits.append(std.get('business_email'))
    if _is_yes(std.get('include_license','No')) and std.get('business_license'):
        meta_bits.append(f"License: {std.get('business_license')}")
    if REPORTLAB_OK:
        styles = getSampleStyleSheet()
        normal = ParagraphStyle('jrc_normal', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=13)
        small = ParagraphStyle('jrc_small', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor('#475569'))
        header = ParagraphStyle('jrc_header', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=17, textColor=colors.HexColor('#111827'))
        doc = SimpleDocTemplate(str(path), pagesize=letter, rightMargin=.6*inch, leftMargin=.6*inch, topMargin=.55*inch, bottomMargin=.55*inch)
        story = []
        story.append(Paragraph(business, header))
        story.append(Paragraph(' | '.join(meta_bits), normal))
        story.append(Paragraph(f'Owned and operated by {owner}', small))
        story.append(Spacer(1, .18*inch))
        story.append(Paragraph(f'<b>{doc_type.upper()}</b> &nbsp;&nbsp; {doc_no}', normal))
        story.append(Paragraph(f"<b>Customer:</b> {job['customer']}<br/><b>Job:</b> {job['job_name']}<br/><b>Address:</b> {job['job_address'] or job['caddr'] or ''}", normal))
        story.append(Spacer(1, .18*inch))
        story.append(Paragraph('<b>Scope of Work</b>', normal))
        for para in (scope or '').split('\n'):
            if para.strip(): story.append(Paragraph(para.strip(), normal))
        story.append(Spacer(1, .18*inch))
        data = [['Total Customer Price', money(price)], ['Deposit Due Before Work Begins', money(deposit)], ['Balance Due Upon Completion', money(balance)]]
        table = Table(data, colWidths=[3.25*inch, 2*inch])
        table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#dcfce7')),('GRID', (0,0), (-1,-1), 0.5, colors.grey),('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),('ALIGN', (1,0), (1,-1), 'RIGHT'),('PADDING', (0,0), (-1,-1), 8)]))
        story.append(table)
        story.append(Spacer(1, .18*inch))
        story.append(Paragraph(f'<b>Payment Terms</b><br/>{terms}', normal))
        story.append(Spacer(1, .08*inch))
        story.append(Paragraph(f'<b>Notes / Exclusions</b><br/>{exclusions}', normal))
        story.append(Spacer(1, .12*inch))
        story.append(Paragraph('<i>Customer-facing copy. Internal cost sheets, helper payment notes, and tax/profit notes are excluded by J&R standard.</i>', small))
        if show_sig:
            story.append(Spacer(1, .35*inch))
            story.append(Paragraph('Customer Signature: ____________________________ &nbsp;&nbsp; Date: ____________', normal))
        doc.build(story)
    else:
        path = EXPORT_DIR / f'{safe}.html'
        css = 'body{font-family:Arial,sans-serif;max-width:850px;margin:28px auto;color:#111827}h1{margin-bottom:0}.muted{color:#475569}table{border-collapse:collapse;margin:20px 0}td{border:1px solid #999;padding:8px 14px}td:last-child{text-align:right;font-weight:bold}'
        html_text = '<html><head><meta charset="utf-8"><title>{0} {1}</title><style>{2}</style></head><body>'.format(doc_type, doc_no, css)
        html_text += '<h1>{}</h1><p>{}<br><span class="muted">Owned and operated by {}</span></p>'.format(business, ' | '.join(meta_bits), owner)
        html_text += '<h2>{} {}</h2><p><b>Customer:</b> {}<br><b>Job:</b> {}<br><b>Address:</b> {}</p>'.format(doc_type, doc_no, job['customer'], job['job_name'], job['job_address'] or job['caddr'] or '')
        html_text += '<h3>Scope of Work</h3><pre>{}</pre><h3>Price</h3>'.format(scope)
        html_text += '<table><tr><td>Total Customer Price</td><td>{}</td></tr><tr><td>Deposit Due Before Work Begins</td><td>{}</td></tr><tr><td>Balance Due Upon Completion</td><td>{}</td></tr></table>'.format(money(price), money(deposit), money(balance))
        html_text += '<h3>Payment Terms</h3><p>{}</p><h3>Notes / Exclusions</h3><p>{}</p><p class="muted"><i>Customer-facing copy. Internal cost sheets, helper payment notes, and tax/profit notes are excluded by J&R standard.</i></p></body></html>'.format(terms, exclusions)
        path.write_text(html_text, encoding='utf-8')
    return path

DarkApp.generate_document_pdf = _v25_generate_document_pdf

_prev_export_all_reports_v25 = DarkApp.export_all_reports

def _v25_export_all_reports(self):
    _ensure_business_standards(self.db)
    _prev_export_all_reports_v25(self)
    self.db.log('Business Standards', 'Included current business standards in export set.')

DarkApp.export_all_reports = _v25_export_all_reports
# ---------------- END JRC_MANAGER_V25_BUSINESS_STANDARDS_EXTENSION ----------------

# ---------------- JRC_MANAGER_V26_OWNER_ACCOUNT_RECOVERY_SOURCES_UI ----------------
OWNER_DEFAULT_EMAIL = 'enragementwow@hotmail.com'
OWNER_ADMIN_USERNAME = 'admin'


def _v26_add_column_if_missing(db, table, col_def):
    name = col_def.split()[0]
    try:
        cols = [r['name'] for r in db.q(f"PRAGMA table_info({table})")]
        if name not in cols:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
    except Exception as e:
        try: db.log('System', f'Could not add column {table}.{name}: {e}')
        except Exception: pass

_prev_v26_init_schema = Database.init_schema

def _v26_init_schema(self):
    _prev_v26_init_schema(self)
    for col in ['email TEXT','recovery_email TEXT','phone TEXT','title TEXT','account_notes TEXT','updated_at TEXT']:
        _v26_add_column_if_missing(self, 'users', col)
    self.conn.commit()

Database.init_schema = _v26_init_schema

_prev_v26_seed_defaults = Database.seed_defaults

def _v26_seed_defaults(self):
    _prev_v26_seed_defaults(self)
    row = self.one('SELECT * FROM users WHERE username=?', (OWNER_ADMIN_USERNAME,))
    if row:
        try:
            updates=[]; params=[]
            pairs=[('full_name','Jacob Cosentino'),('email',OWNER_DEFAULT_EMAIL),('recovery_email',OWNER_DEFAULT_EMAIL),('title','Owner / Administrator'),('account_notes','Primary J and R Construction owner account. Laptop registered as trusted administrator device.')]
            for col,val in pairs:
                try:
                    if not row[col]:
                        updates.append(f'{col}=?'); params.append(val)
                except Exception: pass
            if updates:
                params += [iso_now(), row['id']]
                self.execute(f"UPDATE users SET {', '.join(updates)}, updated_at=? WHERE id=?", params)
        except Exception:
            pass
    self.set_setting('owner_admin_username', OWNER_ADMIN_USERNAME)
    self.set_setting('owner_default_email', OWNER_DEFAULT_EMAIL)
    self.set_setting('program_display_version', APP_VERSION)
    _v26_seed_file_sources(self, quiet=True)

Database.seed_defaults = _v26_seed_defaults


def _possible_windows_sources():
    userprofile = os.environ.get('USERPROFILE') or str(Path.home())
    p = Path(userprofile)
    return [
        ('Dropbox Business Folder - Invoices2026 1.0','DropboxLocal',p/'Dropbox'/'Invoices2026 1.0'),
        ('Dropbox Business Folder - J and R Construction','DropboxLocal',p/'Dropbox'/'J and R Construction'),
        ('Dropbox Business Folder - JRC','DropboxLocal',p/'Dropbox'/'JRC'),
        ('OneDrive Desktop - Invoices2026 1.0','LocalFolder',p/'OneDrive'/'Desktop'/'Invoices2026 1.0'),
        ('OneDrive Desktop - J and R Construction','LocalFolder',p/'OneDrive'/'Desktop'/'J and R Construction'),
        ('Documents - JRC','LocalFolder',p/'Documents'/'JRC'),
        ('C Drive - JRC','LocalFolder',Path('C:/JRC')),
        ('Program Evidence','LocalEvidence',EVIDENCE_DIR),
        ('Program Exports','LocalExports',EXPORT_DIR),
        ('ChatGPT Imports','ChatGPT',CHATGPT_IMPORTS_DIR),
    ]


def _v26_seed_file_sources(db, quiet=False):
    try:
        for folder in [EVIDENCE_DIR, EXPORT_DIR, CHATGPT_IMPORTS_DIR, BASE_DIR/'backups']:
            folder.mkdir(parents=True, exist_ok=True)
        existing = db.get_setting('dropbox_folder','')
        for name, typ, root in _possible_windows_sources():
            root_str = str(root)
            enabled = 1 if root.exists() or typ in ('LocalEvidence','LocalExports','ChatGPT') else 0
            notes = 'Preset by J and R Construction Manager for Jacob admin account. Enable after folder exists.'
            db.execute("INSERT INTO file_sources(source_name,source_type,root_path,enabled,notes) VALUES(?,?,?,?,?) ON CONFLICT(source_name) DO UPDATE SET source_type=excluded.source_type, root_path=excluded.root_path", (name,typ,root_str,enabled,notes))
            if enabled and typ == 'DropboxLocal' and not existing:
                db.set_setting('dropbox_folder', root_str); existing = root_str
        if not quiet: db.log('File Sources','Preset Windows/Dropbox/ChatGPT/evidence file sources for owner admin account.')
    except Exception as e:
        try: db.log('File Sources', f'Could not preset sources: {e}')
        except Exception: pass


def _v26_send_email(db, to_addr, subject, body):
    host = db.get_setting('smtp_host','').strip()
    port = int(db.get_setting('smtp_port','587') or 587)
    user = db.get_setting('smtp_user','').strip()
    pw = db.get_setting('smtp_password','')
    from_addr = db.get_setting('smtp_from','').strip() or user
    if not host or not from_addr:
        raise RuntimeError('Email recovery is not configured yet. Set SMTP email settings inside Admin first.')
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject; msg['From'] = from_addr; msg['To'] = to_addr
    with smtplib.SMTP(host, port, timeout=20) as server:
        server.starttls()
        if user: server.login(user, pw)
        server.send_message(msg)


def _v26_temp_password():
    return 'JRC-' + secrets.token_urlsafe(8).replace('-', '').replace('_', '')[:10]


def _v26_login_init(self, parent, db):
    tk.Toplevel.__init__(self, parent)
    self.db = db; self.result = None
    self.title('J and R Construction Manager Login')
    self.configure(bg=DARK_BG); self.resizable(False, False); self.grab_set(); self.protocol('WM_DELETE_WINDOW', self.cancel)
    outer = tk.Frame(self, bg=DARK_BG); outer.pack(fill='both', expand=True, padx=22, pady=22)
    hero = tk.Frame(outer, bg=CARD_BG, bd=0, highlightthickness=1, highlightbackground='#334155'); hero.pack(fill='both', expand=True)
    banner = tk.Frame(hero, bg=PANEL_BG); banner.grid(row=0, column=0, columnspan=2, sticky='ew')
    tk.Label(banner, text='J & R', bg=PANEL_BG, fg=ACCENT, font=('Segoe UI', 28, 'bold')).pack(side='left', padx=(18,10), pady=14)
    tk.Label(banner, text='Construction Manager', bg=PANEL_BG, fg=TEXT, font=('Segoe UI', 18, 'bold')).pack(side='left', pady=14)
    tk.Label(hero, text='Owned and operated by Jacob Cosentino', bg=CARD_BG, fg=MUTED, font=('Segoe UI', 10)).grid(row=1, column=0, columnspan=2, sticky='w', padx=22, pady=(16,8))
    tk.Label(hero, text='Secure business operations, job records, documents, and file sources.', bg=CARD_BG, fg=TEXT, font=('Segoe UI', 10)).grid(row=2, column=0, columnspan=2, sticky='w', padx=22, pady=(0,16))
    tk.Label(hero, text='Username', bg=CARD_BG, fg=TEXT, font=('Segoe UI', 10, 'bold')).grid(row=3, column=0, sticky='w', padx=22, pady=6)
    self.username = ttk.Entry(hero, width=34); self.username.grid(row=3, column=1, padx=22, pady=6)
    tk.Label(hero, text='Password', bg=CARD_BG, fg=TEXT, font=('Segoe UI', 10, 'bold')).grid(row=4, column=0, sticky='w', padx=22, pady=6)
    self.password = ttk.Entry(hero, width=34, show='*'); self.password.grid(row=4, column=1, padx=22, pady=6)
    trusted = db.get_setting('trusted_admin_device_id', '') == get_device_id()
    tk.Label(hero, text=('Trusted owner laptop recognized.' if trusted else 'This device is not the original owner/admin laptop.'), bg=CARD_BG, fg=ACCENT if trusted else WARNING, wraplength=440, font=('Segoe UI', 9, 'bold')).grid(row=5, column=0, columnspan=2, sticky='w', padx=22, pady=(10,4))
    tk.Label(hero, text='Default first login: admin / admin. Change it in Owner/Admin settings.', bg=CARD_BG, fg=MUTED, wraplength=440, font=('Segoe UI', 9)).grid(row=6, column=0, columnspan=2, sticky='w', padx=22, pady=(0,12))
    btns = tk.Frame(hero, bg=CARD_BG); btns.grid(row=7, column=0, columnspan=2, sticky='ew', padx=22, pady=(6,20))
    ttk.Button(btns, text='Forgot Password', command=self.forgot_password).pack(side='left')
    ttk.Button(btns, text='Cancel', command=self.cancel).pack(side='right', padx=5)
    ttk.Button(btns, text='Login', style='Accent.TButton', command=self.login).pack(side='right', padx=5)
    hero.columnconfigure(1, weight=1)
    self.username.insert(0, 'admin'); self.password.focus_set(); self.bind('<Return>', lambda e: self.login())
    self.update_idletasks(); self.geometry(f"+{parent.winfo_screenwidth()//2 - self.winfo_width()//2}+{parent.winfo_screenheight()//2 - self.winfo_height()//2}")


def _v26_forgot_password(self):
    win = tk.Toplevel(self); win.title('Account Recovery'); win.configure(bg=DARK_BG); win.resizable(False, False)
    f = ttk.Frame(win, style='Card.TFrame', padding=16); f.pack(fill='both', expand=True, padx=12, pady=12)
    ttk.Label(f, text='Account Recovery', style='CardHeader.TLabel').grid(row=0, column=0, columnspan=2, sticky='w', pady=(0,8))
    ttk.Label(f, text='Enter the username and recovery email listed on that account. The program creates a temporary password and emails it when SMTP is configured.', background=CARD_BG, foreground=MUTED, wraplength=420).grid(row=1, column=0, columnspan=2, sticky='w', pady=(0,10))
    u = tk.StringVar(value='admin'); e = tk.StringVar(value='')
    ttk.Label(f, text='Username', background=CARD_BG).grid(row=2, column=0, sticky='w', pady=4); ttk.Entry(f, textvariable=u, width=34).grid(row=2, column=1, pady=4)
    ttk.Label(f, text='Recovery Email', background=CARD_BG).grid(row=3, column=0, sticky='w', pady=4); ttk.Entry(f, textvariable=e, width=34).grid(row=3, column=1, pady=4)
    def recover():
        username = u.get().strip(); email = e.get().strip().lower()
        row = self.db.one('SELECT * FROM users WHERE username=? AND active=1', (username,))
        stored = ((row['recovery_email'] or row['email'] or '').strip().lower() if row else '')
        if not row or not stored or stored != email:
            messagebox.showerror('Recovery failed', 'The username and recovery email did not match an active account.'); return
        temp = _v26_temp_password(); salt, ph = hash_password(temp)
        self.db.execute('UPDATE users SET salt=?, password_hash=?, must_change_password=1, updated_at=? WHERE id=?', (salt, ph, iso_now(), row['id']))
        body = f"J and R Construction Manager password recovery\n\nAccount: {username}\nTemporary password: {temp}\n\nLog in and change this password immediately.\n\nOwned and operated by Jacob Cosentino / J & R Construction."
        try:
            _v26_send_email(self.db, stored, 'J and R Construction Manager account recovery', body)
            self.db.log('Security', f'Password recovery email sent for {username}.')
            messagebox.showinfo('Recovery sent', 'A temporary password was sent to the recovery email.'); win.destroy()
        except Exception as ex:
            trusted = self.db.get_setting('trusted_admin_device_id','') == get_device_id()
            self.db.log('Security', f'Password recovery generated for {username}, email delivery failed: {ex}')
            if trusted and username == OWNER_ADMIN_USERNAME:
                messagebox.showwarning('Email not configured', f'Email sending is not configured or failed. Because this is the trusted owner laptop, here is the temporary password:\n\n{temp}\n\nChange it immediately after login.\n\nEmail error: {ex}'); win.destroy()
            else:
                messagebox.showerror('Email not configured', str(ex))
    ttk.Button(f, text='Send Recovery / Reset', style='Accent.TButton', command=recover).grid(row=4, column=1, sticky='e', pady=10)

LoginDialog.__init__ = _v26_login_init
LoginDialog.forgot_password = _v26_forgot_password


def _v26_owner_account_center(self):
    row = self.db.one('SELECT * FROM users WHERE username=?', (OWNER_ADMIN_USERNAME,))
    if not row: messagebox.showerror('Missing owner account','Owner admin account was not found.'); return
    win = tk.Toplevel(self); win.title('Owner Account Center'); win.configure(bg=DARK_BG); win.geometry('620x520')
    f = ttk.Frame(win, style='Card.TFrame', padding=16); f.pack(fill='both', expand=True, padx=12, pady=12)
    ttk.Label(f, text='Owner Account Center', style='CardHeader.TLabel').grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,8))
    fields=[('Full Name','full_name'),('Title','title'),('Email','email'),('Recovery Email','recovery_email'),('Phone','phone'),('Notes','account_notes')]
    vars={}
    for i,(label,col) in enumerate(fields, start=1):
        ttk.Label(f,text=label,background=CARD_BG).grid(row=i,column=0,sticky='w',padx=4,pady=5)
        v=tk.StringVar(value=row[col] if col in row.keys() and row[col] else ''); ttk.Entry(f,textvariable=v,width=48).grid(row=i,column=1,sticky='ew',padx=4,pady=5); vars[col]=v
    ttk.Label(f,text='New Password',background=CARD_BG).grid(row=7,column=0,sticky='w',padx=4,pady=5)
    newpw=ttk.Entry(f,show='*',width=48); newpw.grid(row=7,column=1,sticky='ew',padx=4,pady=5)
    ttk.Label(f,text='Leave password blank to keep current password. Keep recovery email current before using Forgot Password.',background=CARD_BG,foreground=MUTED,wraplength=500).grid(row=8,column=0,columnspan=2,sticky='w',pady=8)
    def save():
        self.db.execute('UPDATE users SET full_name=?, title=?, email=?, recovery_email=?, phone=?, account_notes=?, updated_at=? WHERE id=?', (vars['full_name'].get().strip(),vars['title'].get().strip(),vars['email'].get().strip(),vars['recovery_email'].get().strip(),vars['phone'].get().strip(),vars['account_notes'].get().strip(),iso_now(),row['id']))
        if newpw.get().strip():
            salt, ph = hash_password(newpw.get().strip()); self.db.execute('UPDATE users SET salt=?, password_hash=?, must_change_password=0, updated_at=? WHERE id=?', (salt, ph, iso_now(), row['id']))
        self.db.log('Admin', 'Owner admin account updated from Owner Account Center.'); messagebox.showinfo('Saved','Owner account updated.'); win.destroy(); self.refresh_users()
    ttk.Button(f,text='Save Owner Account',style='Accent.TButton',command=save).grid(row=9,column=1,sticky='e',pady=10); f.columnconfigure(1,weight=1)


def _v26_email_settings_window(self):
    win=tk.Toplevel(self); win.title('Email Recovery Settings'); win.configure(bg=DARK_BG); win.geometry('620x430')
    f=ttk.Frame(win,style='Card.TFrame',padding=16); f.pack(fill='both',expand=True,padx=12,pady=12)
    ttk.Label(f,text='Email Recovery Settings',style='CardHeader.TLabel').grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,8))
    ttk.Label(f,text='Used only to email temporary password reset messages. Use an app password, not your main email password.',background=CARD_BG,foreground=MUTED,wraplength=520).grid(row=1,column=0,columnspan=2,sticky='w',pady=(0,10))
    keys=[('SMTP Host','smtp_host'),('SMTP Port','smtp_port'),('SMTP Username','smtp_user'),('SMTP Password / App Password','smtp_password'),('From Email','smtp_from')]
    vars={}
    for i,(label,key) in enumerate(keys,start=2):
        ttk.Label(f,text=label,background=CARD_BG).grid(row=i,column=0,sticky='w',padx=4,pady=5)
        v=tk.StringVar(value=self.db.get_setting(key,'587' if key=='smtp_port' else '')); ttk.Entry(f,textvariable=v,width=45,show='*' if key=='smtp_password' else '').grid(row=i,column=1,sticky='ew',padx=4,pady=5); vars[key]=v
    def save():
        for k,v in vars.items(): self.db.set_setting(k,v.get().strip())
        self.db.log('Admin','Email recovery SMTP settings updated.'); messagebox.showinfo('Saved','Email recovery settings saved.'); win.destroy()
    ttk.Button(f,text='Save Email Settings',style='Accent.TButton',command=save).grid(row=8,column=1,sticky='e',pady=10); f.columnconfigure(1,weight=1)


def _v26_edit_user_window(self):
    uid = self.selected_user_id()
    if not uid: return
    row = self.db.one('SELECT * FROM users WHERE id=?', (uid,))
    if not row: return
    win = tk.Toplevel(self); win.title('Edit User Account'); win.configure(bg=DARK_BG); win.geometry('640x560')
    f = ttk.Frame(win, style='Card.TFrame', padding=16); f.pack(fill='both', expand=True, padx=12, pady=12)
    ttk.Label(f, text='Edit User Account', style='CardHeader.TLabel').grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,8))
    fields=[('Username','username'),('Full Name','full_name'),('Title','title'),('Email','email'),('Recovery Email','recovery_email'),('Phone','phone'),('Notes','account_notes')]
    vars={}
    for i,(label,col) in enumerate(fields, start=1):
        ttk.Label(f,text=label,background=CARD_BG).grid(row=i,column=0,sticky='w',padx=4,pady=5)
        v=tk.StringVar(value=row[col] if col in row.keys() and row[col] else ''); e=ttk.Entry(f,textvariable=v,width=48); e.grid(row=i,column=1,sticky='ew',padx=4,pady=5)
        if col=='username' and row['username']==OWNER_ADMIN_USERNAME: e.configure(state='disabled')
        vars[col]=v
    ttk.Label(f,text='Role',background=CARD_BG).grid(row=8,column=0,sticky='w',padx=4,pady=5)
    role=ttk.Combobox(f,values=['Admin','Manager','Worker','Viewer','User'],state='readonly'); role.set(row['role']); role.grid(row=8,column=1,sticky='w',padx=4,pady=5)
    active_var=tk.IntVar(value=1 if row['active'] else 0); ttk.Checkbutton(f,text='Active account',variable=active_var).grid(row=9,column=1,sticky='w',pady=5)
    ttk.Label(f,text='New Password',background=CARD_BG).grid(row=10,column=0,sticky='w',padx=4,pady=5); newpw=ttk.Entry(f,show='*',width=48); newpw.grid(row=10,column=1,sticky='ew',padx=4,pady=5)
    def save():
        username=vars['username'].get().strip()
        if not username: messagebox.showerror('Missing','Username is required.'); return
        active=1 if row['username']==OWNER_ADMIN_USERNAME else active_var.get(); selected_role='Admin' if row['username']==OWNER_ADMIN_USERNAME else role.get(); username=OWNER_ADMIN_USERNAME if row['username']==OWNER_ADMIN_USERNAME else username
        try:
            self.db.execute('UPDATE users SET username=?, full_name=?, title=?, email=?, recovery_email=?, phone=?, role=?, active=?, account_notes=?, updated_at=? WHERE id=?', (username, vars['full_name'].get().strip(), vars['title'].get().strip(), vars['email'].get().strip(), vars['recovery_email'].get().strip(), vars['phone'].get().strip(), selected_role, active, vars['account_notes'].get().strip(), iso_now(), uid))
            if newpw.get().strip():
                salt, ph=hash_password(newpw.get().strip()); self.db.execute('UPDATE users SET salt=?, password_hash=?, must_change_password=1, updated_at=? WHERE id=?',(salt,ph,iso_now(),uid))
            self.db.log('Admin', f'User account edited: {username}.'); win.destroy(); self.refresh_users()
        except sqlite3.IntegrityError: messagebox.showerror('Username exists','That username already exists.')
    ttk.Button(f,text='Save Changes',style='Accent.TButton',command=save).grid(row=12,column=1,sticky='e',pady=10); f.columnconfigure(1,weight=1)


def _v26_admin_build(self):
    wrap = ttk.Frame(self.admin_tab); wrap.pack(fill='both', expand=True, padx=8, pady=8)
    c = self.card(wrap, 'Owner / Admin Account Control'); c.pack(fill='x', padx=4, pady=4)
    ttk.Label(c, text='Owner account, recovery email, user controls, and preset file sources. Passwords stay hashed in the database.', background=CARD_BG, foreground=MUTED, wraplength=1000).pack(anchor='w', pady=(4,8))
    btns = ttk.Frame(c, style='Card.TFrame'); btns.pack(fill='x')
    ttk.Button(btns, text='Owner Account Center', style='Accent.TButton', command=lambda: _v26_owner_account_center(self)).pack(side='left', padx=3)
    ttk.Button(btns, text='Email Recovery Settings', command=lambda: _v26_email_settings_window(self)).pack(side='left', padx=3)
    ttk.Button(btns, text='Preset This PC File Sources', command=lambda: (_v26_seed_file_sources(self.db), self.scan_sources_now(quiet=True), self.refresh_file_sources(), messagebox.showinfo('Preset Complete','Known local/Dropbox/ChatGPT file sources were preset for this PC.'))).pack(side='left', padx=3)
    c2 = self.card(wrap, 'User Accounts'); c2.pack(fill='both', expand=True, padx=4, pady=4)
    btns2=ttk.Frame(c2, style='Card.TFrame'); btns2.pack(fill='x')
    ttk.Button(btns2,text='Add User',style='Accent.TButton',command=self.add_user_window).pack(side='left',padx=3)
    ttk.Button(btns2,text='Edit Selected Account',command=lambda: _v26_edit_user_window(self)).pack(side='left',padx=3)
    ttk.Button(btns2,text='Reset Password',command=self.reset_user_password).pack(side='left',padx=3)
    ttk.Button(btns2,text='Toggle Active',command=self.toggle_user_active).pack(side='left',padx=3)
    ttk.Button(btns2,text='Export Account Index',command=self.export_user_index).pack(side='left',padx=3)
    self.users_tree = self.make_tree(c2, ['ID','Username','Full Name','Role','Active','Email','Recovery Email','Last Login'], height=22); self.refresh_users()
DarkApp.build_admin = _v26_admin_build


def _v26_refresh_users(self):
    if not hasattr(self,'users_tree'): return
    self.clear_tree(self.users_tree)
    rows=self.db.q('SELECT id,username,full_name,role,active,email,recovery_email,last_login FROM users ORDER BY username')
    for r in rows: self.users_tree.insert('', 'end', values=[r['id'], r['username'], r['full_name'] or '', r['role'], 'Yes' if r['active'] else 'No', r['email'] or '', r['recovery_email'] or '', r['last_login'] or ''])
DarkApp.refresh_users = _v26_refresh_users


def _v26_add_user_window(self):
    win=tk.Toplevel(self); win.title('Add User'); win.configure(bg=DARK_BG); win.geometry('600x520')
    f=ttk.Frame(win,style='Card.TFrame',padding=16); f.pack(fill='both',expand=True,padx=12,pady=12)
    ttk.Label(f,text='Add User Account',style='CardHeader.TLabel').grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,8))
    fields=['Username','Full Name','Title','Email','Recovery Email','Phone','Password']; vars={}
    for i,label in enumerate(fields,start=1):
        ttk.Label(f,text=label,background=CARD_BG).grid(row=i,column=0,sticky='w',padx=4,pady=4); v=tk.StringVar(); ttk.Entry(f,textvariable=v,width=42,show='*' if label=='Password' else '').grid(row=i,column=1,sticky='ew',padx=4,pady=4); vars[label]=v
    ttk.Label(f,text='Role',background=CARD_BG).grid(row=8,column=0,sticky='w',padx=4,pady=4); role=ttk.Combobox(f,values=['Admin','Manager','Worker','Viewer','User'],state='readonly'); role.set('Viewer'); role.grid(row=8,column=1,sticky='w',padx=4,pady=4)
    def save():
        username=vars['Username'].get().strip(); pw=vars['Password'].get()
        if not username or not pw: messagebox.showerror('Missing','Username and password are required.'); return
        salt,ph=hash_password(pw)
        try:
            self.db.execute('INSERT INTO users(username, full_name, title, email, recovery_email, phone, role, salt, password_hash, active, must_change_password, created_at, account_notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (username, vars['Full Name'].get().strip(), vars['Title'].get().strip(), vars['Email'].get().strip(), vars['Recovery Email'].get().strip(), vars['Phone'].get().strip(), role.get(), salt, ph, 1, 1, iso_now(), 'Added by admin'))
            self.db.log('Admin', f'User account added: {username} ({role.get()}).'); win.destroy(); self.refresh_users()
        except sqlite3.IntegrityError: messagebox.showerror('Exists','That username already exists.')
    ttk.Button(f,text='Save User',style='Accent.TButton',command=save).grid(row=9,column=1,sticky='e',pady=10); f.columnconfigure(1,weight=1)
DarkApp.add_user_window = _v26_add_user_window


def _v26_export_user_index(self):
    path = EXPORT_DIR / 'JRC_User_Accounts_Admin_Index.csv'
    rows = self.db.q('SELECT username, full_name, title, role, active, email, recovery_email, phone, created_at, last_login, account_notes, notes FROM users ORDER BY username')
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['Username','Full Name','Title','Role','Active','Email','Recovery Email','Phone','Created','Last Login','Password Storage','Notes'])
        for r in rows: w.writerow([r['username'], r['full_name'] or '', r['title'] or '', r['role'], 'Yes' if r['active'] else 'No', r['email'] or '', r['recovery_email'] or '', r['phone'] or '', r['created_at'], r['last_login'] or '', 'Hashed in SQLite database - not plain text', r['account_notes'] or r['notes'] or ''])
    messagebox.showinfo('Exported', str(path))
DarkApp.export_user_index = _v26_export_user_index

_prev_v26_refresh_all = DarkApp.refresh_all

def _v26_refresh_all(self):
    _v26_seed_file_sources(self.db, quiet=True)
    _prev_v26_refresh_all(self)
DarkApp.refresh_all = _v26_refresh_all
# ---------------- END JRC_MANAGER_V26_OWNER_ACCOUNT_RECOVERY_SOURCES_UI ----------------


if __name__ == "__main__":
    app = DarkApp()
    app.mainloop()
