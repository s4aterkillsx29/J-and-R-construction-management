"""
J and R Construction Manager - Network Server Edition
Owned and operated by Jacob Cosentino / J & R Construction.
This server is cloud-primary for live business use.
Recommended live pattern: one HTTPS cloud service with persistent storage, health checks,
owner/admin security, and role-based portals. Local LAN hosting remains a fallback only.
"""
import csv
import datetime as dt
import functools
import hashlib
import html
import json
import os
import platform
import secrets
import shutil
import socket
import sqlite3
import sys
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
try:
    from flask import Flask, Response, abort, flash, g, jsonify, redirect, render_template_string, request, send_file, session, url_for
except Exception as exc:
    print("Flask is required. Run INSTALL_JR_JOB_MANAGER.bat first.")
    raise
APP_NAME = "J and R Construction Manager"
APP_VERSION = "7.13.0 Densus Owner-Approval Edition"
BUSINESS_NAME = "J & R Construction"
OWNER = "Jacob Cosentino"
PHONE = "(910) 712-0936"
BASE_DIR = Path(__file__).resolve().parents[1]
# Cloud-primary data locations.
# Local desktop keeps data inside the install folder. Cloud deployments should set JRC_DATA_DIR
# to a persistent volume path so the live database/files survive deploys and restarts.
DATA_DIR = Path(os.environ.get("JRC_DATA_DIR", str(BASE_DIR / "data"))).expanduser()
EXPORT_DIR = Path(os.environ.get("JRC_EXPORT_DIR", str(BASE_DIR / "exports"))).expanduser()
EVIDENCE_DIR = Path(os.environ.get("JRC_EVIDENCE_DIR", str(BASE_DIR / "evidence"))).expanduser()
CHATGPT_IMPORTS_DIR = Path(os.environ.get("JRC_CHATGPT_IMPORTS_DIR", str(BASE_DIR / "chatgpt_imports"))).expanduser()
BACKUP_DIR = Path(os.environ.get("JRC_BACKUP_DIR", str(BASE_DIR / "backups"))).expanduser()
DB_PATH = Path(os.environ.get("JRC_DB_PATH", str(DATA_DIR / "jr_business.db"))).expanduser()
SERVER_SECRET_PATH = DATA_DIR / "server_secret.key"
DEVICE_ID_PATH = DATA_DIR / "trusted_device_id.txt"
SERVER_SETTINGS_PATH = DATA_DIR / "network_server_settings.json"
SESSION_TIMEOUT_MINUTES = int(os.environ.get("JRC_SESSION_TIMEOUT_MINUTES", "120"))
PUBLIC_HOST_MODE = os.environ.get("JRC_PUBLIC_HOST_MODE", "0") == "1"
CLOUD_PRIMARY_MODE = os.environ.get("JRC_CLOUD_PRIMARY_MODE", "0") == "1" or PUBLIC_HOST_MODE
REQUIRE_STRONG_DEFAULT_PASSWORD_CHANGE = True
from app.role_utils import DEFAULT_OWNER_USERNAME as DEFAULT_ADMIN_USERNAME

DEFAULT_ADMIN_PASSWORD = "ivygrows"
CLOUD_INITIAL_ADMIN_PASSWORD = os.environ.get("JRC_INITIAL_ADMIN_PASSWORD", "").strip()
ALLOW_LOCAL_DEFAULT_ADMIN = os.environ.get("JRC_ALLOW_LOCAL_DEFAULT_ADMIN", "1") == "1"
# Secure remembered-device cookie settings.
# The device cookie is only an opaque random token; the database stores only its SHA-256 fingerprint.
# Secure=True is automatically used for HTTPS/public host mode. Local/LAN HTTP keeps the cookie working
# while still using HttpOnly + SameSite + server-side hashing/audit logs.
DEVICE_COOKIE_NAME = "jrc_device_token"
DEVICE_COOKIE_MAX_AGE_SECONDS = int(os.environ.get("JRC_DEVICE_COOKIE_DAYS", "90")) * 24 * 60 * 60
DEVICE_COOKIE_SAMESITE = os.environ.get("JRC_DEVICE_COOKIE_SAMESITE", "Strict")
for folder in [DATA_DIR, EXPORT_DIR, EVIDENCE_DIR, CHATGPT_IMPORTS_DIR, BACKUP_DIR]:
    folder.mkdir(parents=True, exist_ok=True)
from app.role_permissions import PERMISSIONS, ROLE_LABELS, ROLE_DISPLAY_NAMES, HIRE_APPLICATION_ROLES
ROLE_RANK = {role: index for index, role in enumerate(ROLE_LABELS)}
def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")
def now_display() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %I:%M %p")
def money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "$0.00"
def parse_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except Exception:
        return 0.0
def get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
def get_device_id() -> str:
    if DEVICE_ID_PATH.exists():
        value = DEVICE_ID_PATH.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = str(uuid.uuid4())
    DEVICE_ID_PATH.write_text(value, encoding="utf-8")
    return value
def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 250000).hex()
    return salt, digest
def verify_password(password: str, salt: str, password_hash: str) -> bool:
    _, digest = hash_password(password, salt)
    if secrets.compare_digest(digest, password_hash):
        return True
    # Legacy desktop builds used 200000 PBKDF2 iterations. Accept once and let login/setup migrate on password change.
    legacy = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000).hex()
    return secrets.compare_digest(legacy, password_hash)
def client_ip() -> str:
    """Return a useful client IP for local LAN, VPN, or a future reverse proxy."""
    try:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.remote_addr or "unknown"
    except Exception:
        return "unknown"
def password_quality(password: str, admin_change: bool = False) -> tuple[bool, str]:
    """Password rules — Densus policy aligned with JRC roles."""
    from app.first_setup_security import check_password_change_allowed, is_forbidden_owner_password
    if is_forbidden_owner_password(password):
        return False, "Cannot use first-setup or common default passwords."
    role = "admin" if admin_change else "worker"
    from app.densus_policy import enforce_densus_password
    return enforce_densus_password(password, role)


def enforce_new_password_policy(new_password: str, mastery_key: str = "", role: str = "") -> tuple[bool, str]:
    from app.first_setup_security import check_password_change_allowed
    ok, msg = check_password_change_allowed(new_password, mastery_key)
    if not ok:
        return ok, msg
    if not role:
        try:
            from flask import session as flask_session
            role = flask_session.get("role", "worker") or "worker"
        except Exception:
            role = "worker"
    from app.densus_policy import enforce_densus_password
    return enforce_densus_password(new_password, role)

def is_local_setup_request() -> bool:
    """True only for the computer running the local app, not remote/customer users."""
    ip = client_ip()
    return ip in {"127.0.0.1", "::1", "localhost"}

def get_setting_direct(conn, key: str, default: str = "") -> str:
    try:
        row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row and row["value"] is not None else default
    except Exception:
        return default

def is_default_admin_password_active_conn(conn) -> bool:
    row = conn.execute("SELECT salt,password_hash FROM users WHERE username=? AND active=1", (DEFAULT_ADMIN_USERNAME,)).fetchone()
    return bool(row and verify_password(DEFAULT_ADMIN_PASSWORD, row["salt"], row["password_hash"]))

def is_default_admin_password_active() -> bool:
    try:
        return is_default_admin_password_active_conn(db())
    except Exception:
        return False

def mark_admin_password_changed(conn=None) -> None:
    target = conn or db()
    target.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("admin_default_password_changed", "1"))
    target.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("owner_setup_complete", "1"))
    target.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("admin_default_login_disabled_after_change", "1"))
    target.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("admin_password_changed_at", now_iso()))
    if conn is None:
        target.commit()
def log_security_event(event_type: str, username: str = "", message: str = "", level: str = "INFO") -> None:
    try:
        with direct_db() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, event_time TEXT, level TEXT, event_type TEXT,
                username TEXT, ip_address TEXT, user_agent TEXT, message TEXT
            )""")
            conn.execute("INSERT INTO security_events (event_time,level,event_type,username,ip_address,user_agent,message) VALUES (?,?,?,?,?,?,?)",
                         (now_iso(), level, event_type, username, client_ip(), request.headers.get("User-Agent", "") if request else "", message))
            conn.commit()
    except Exception:
        pass
def _hash_device_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()
def get_client_device_token() -> str:
    token = request.cookies.get(DEVICE_COOKIE_NAME, "") if request else ""
    return token if validate_device_token(token) else ""
def make_client_device_token() -> str:
    return secrets.token_urlsafe(48)
def is_https_request() -> bool:
    try:
        return bool(request.is_secure or request.headers.get("X-Forwarded-Proto", "").lower() == "https")
    except Exception:
        return False
def cookie_secure_flag() -> bool:
    # Secure cookies require HTTPS. Use Secure for cloud/tunnel/public host mode or detected HTTPS.
    # Local laptop/LAN http cannot use Secure cookies or the browser will drop them.
    return bool(PUBLIC_HOST_MODE or is_https_request())
def set_secure_device_cookie(resp, token: str):
    resp.set_cookie(
        DEVICE_COOKIE_NAME,
        token,
        max_age=DEVICE_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=cookie_secure_flag(),
        samesite=DEVICE_COOKIE_SAMESITE,
        path="/",
    )
    return resp
def clear_device_cookie(resp):
    resp.delete_cookie(DEVICE_COOKIE_NAME, path="/")
    return resp
def validate_device_token(token: str) -> bool:
    # Accept only URL-safe random-looking tokens created by this program.
    if not token or len(token) < 32 or len(token) > 160:
        return False
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    return all(ch in allowed for ch in token)
def client_device_label(user_agent: str = "") -> str:
    ua = user_agent or (request.headers.get("User-Agent", "") if request else "")
    lowered = ua.lower()
    if "iphone" in lowered:
        return "iPhone browser"
    if "android" in lowered:
        return "Android browser"
    if "ipad" in lowered:
        return "iPad browser"
    if "windows" in lowered:
        return "Windows browser"
    if "mac" in lowered:
        return "Mac browser"
    return "Browser device"
def record_known_device(user_id: int, username: str, token: str, user_agent: str = "", remember_consent: bool = True) -> str:
    """Record a browser/device only after the user consents on login.
    The cookie value is never stored directly. Only a SHA-256 fingerprint is saved.
    Consent expires after 90 days, which forces the user to verify again by logging in
    and checking the remember-device box again.
    """
    if not token or not remember_consent:
        return "not_remembered"
    fingerprint = _hash_device_token(token)
    ua = user_agent or (request.headers.get("User-Agent", "") if request else "")
    ip = client_ip()
    label = client_device_label(ua)
    verified = now_iso()
    expires = (dt.datetime.now() + dt.timedelta(seconds=DEVICE_COOKIE_MAX_AGE_SECONDS)).isoformat(timespec="seconds")
    row = db().execute("SELECT * FROM known_devices WHERE device_fingerprint=?", (fingerprint,)).fetchone()
    if row:
        db().execute("""UPDATE known_devices SET user_id=?, username=?, device_label=?, last_ip=?, last_user_agent=?, last_seen=?, last_verified_at=?, expires_at=?, remember_consent=1
                      WHERE device_fingerprint=?""", (user_id, username, label, ip, ua, now_iso(), verified, expires, fingerprint))
        return row["trust_status"] or "observed"
    db().execute("""INSERT INTO known_devices (user_id, username, device_fingerprint, device_label, first_ip, last_ip, first_user_agent, last_user_agent, first_seen, last_seen, last_verified_at, expires_at, remember_consent, trust_status)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (user_id, username, fingerprint, label, ip, ip, ua, ua, now_iso(), now_iso(), verified, expires, 1, "observed"))
    log_security_event("device_observed", username, f"New remembered device consented: {label} from {ip}; expires {expires}", "INFO")
    return "observed"
def is_client_device_blocked(token: str) -> bool:
    if not token:
        return False
    try:
        row = db().execute("SELECT trust_status, expires_at FROM known_devices WHERE device_fingerprint=?", (_hash_device_token(token),)).fetchone()
        if not row:
            return False
        exp = row["expires_at"] if "expires_at" in row.keys() else ""
        if exp and exp < now_iso():
            return False
        return bool(row and row["trust_status"] == "blocked")
    except Exception:
        return False
def trusted_owner_local_request() -> bool:
    # Transparent, logged owner recovery only from the computer running this company program.
    # This is not a hidden backdoor and does not access other users' devices.
    try:
        trusted_id = db().execute("SELECT value FROM app_settings WHERE key='trusted_admin_device_id'").fetchone()
        local_ip = client_ip() in {"127.0.0.1", "::1", "localhost"}
        return bool(trusted_id and trusted_id["value"] == get_device_id() and local_ip)
    except Exception:
        return False
def request_rate_limited(ip: str) -> bool:
    """Prevent accidental/spam account request flooding while keeping setup easy."""
    cutoff = (dt.datetime.now() - dt.timedelta(hours=24)).isoformat(timespec="seconds")
    try:
        row = db().execute("SELECT COUNT(*) FROM account_requests WHERE request_ip=? AND created_at>=?", (ip, cutoff)).fetchone()
        return bool(row and row[0] >= 8)
    except Exception:
        return False
def safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in " ._-/()" else "_" for ch in str(name))
    cleaned = cleaned.strip().replace("..", "_")
    return cleaned or "file"
def has_permission_role(role: str, permission: str) -> bool:
    from app.role_utils import normalize_role
    return permission in PERMISSIONS.get(normalize_role(role), set())
def role_display(role: str) -> str:
    from app.role_utils import role_display as _role_display
    key = normalize_role_for_session(role)
    return ROLE_DISPLAY_NAMES.get(key, _role_display(role))
def normalize_role_for_session(role: str) -> str:
    from app.role_utils import normalize_role
    return normalize_role(role)
def is_admin_role(role: str) -> bool:
    from app.role_utils import is_admin_role as _is_admin_role
    return _is_admin_role(role)
def role_select_options(selected: str = "", *, exclude: tuple[str, ...] = ()) -> str:
  """HTML <option> list with friendly account-type labels for admin forms."""
  parts = []
  sel = normalize_role_for_session(selected or "")
  for r in ROLE_LABELS:
    if r in exclude:
      continue
    label = ROLE_DISPLAY_NAMES.get(r, r)
    parts.append(f'<option value="{html.escape(r)}"{" selected" if r == sel else ""}>{html.escape(label)}</option>')
  return "".join(parts)
def apply_user_role_change(conn: sqlite3.Connection, user: sqlite3.Row, new_role: str, actor: str, *, mastery_key: str = "") -> tuple[bool, str]:
  """Validate and apply account-type change; provision profiles and log security event."""
  old_role = normalize_role_for_session(user["role"] or "viewer")
  new_role = normalize_role_for_session(new_role or old_role)
  if new_role not in ROLE_LABELS:
    return False, "Invalid account type."
  if new_role == old_role:
    return True, "unchanged"
  if int(user["owner_account"] or 0) or user["username"] == DEFAULT_ADMIN_USERNAME:
    if new_role != "admin":
      return False, "Owner account must remain Owner / Admin."
  if new_role == "admin" and old_role != "admin":
    from app.emergency_access import verify_mastery_key
    if not verify_mastery_key((mastery_key or "").strip()):
      return False, "Granting Owner / Admin requires emergency mastery key on the full Edit User page."
  conn.execute("UPDATE users SET role=?, last_profile_update=? WHERE id=?", (new_role, now_iso(), user["id"]))
  from app.account_provisioning import provision_user_role_profiles
  provision_user_role_profiles(conn, int(user["id"]), user["username"], new_role)
  if new_role != old_role:
      conn.execute(
          "UPDATE online_sessions SET active=0, revoked=1, revoke_reason=? WHERE user_id=? AND active=1",
          (f"Account type changed {old_role} -> {new_role} by {actor}", int(user["id"])),
      )
  log_security_event("user_role_changed", user["username"], f"{old_role} -> {new_role} by {actor}", "OK")
  return True, f"Account type for {user['username']} changed: {role_display(old_role)} → {role_display(new_role)}."
def role_can_access_share(viewer_role: str, minimum_role: str) -> bool:
    # Lower rank number means higher privilege. Non-company can access only items shared to non_company.
    if viewer_role == "admin":
        return True
    return ROLE_RANK.get(viewer_role or "non_company", 999) <= ROLE_RANK.get(minimum_role or "viewer", 999)

def shared_counts_for_role(role: str) -> Tuple[int, int]:
    """Count shared files/jobs visible to this role (not global totals)."""
    role = normalize_role_for_session(role)
    all_sf = db().execute("SELECT shared_with_role FROM shared_files WHERE active=1").fetchall()
    all_sj = db().execute("SELECT shared_with_role FROM shared_jobs WHERE active=1").fetchall()
    sf = sum(1 for r in all_sf if role_can_access_share(role, r["shared_with_role"] or "viewer"))
    sj = sum(1 for r in all_sj if role_can_access_share(role, r["shared_with_role"] or "viewer"))
    return sf, sj
def permission_badges(role: str) -> str:
    perms = sorted(PERMISSIONS.get(role or "viewer", set()))
    return " ".join(f"<span class='badge'>{html.escape(p)}</span>" for p in perms)
def is_customer_or_external(role: str) -> bool:
    return normalize_role_for_session(role) in {"customer", "non_company", "guest"}
def forbid_customer_external_admin_surface() -> None:
    role = session.get("role", "")
    if is_customer_or_external(role):
        log_security_event("permission_denied_external", session.get("username", ""), f"Blocked external/customer access to {request.path}", "WARN")
        abort(403)
def safe_under_base(path: Path, allowed_roots: List[Path]) -> bool:
    try:
        rp = path.resolve()
        return any(str(rp).lower().startswith(str(root.resolve()).lower()) for root in allowed_roots if root.exists())
    except Exception:
        return False
def db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        g.db = conn
    return g.db
def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def direct_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn
def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with direct_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            address TEXT,
            notes TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS customer_user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            username TEXT,
            customer_id INTEGER,
            display_name TEXT,
            email TEXT,
            phone TEXT,
            address TEXT,
            portal_status TEXT DEFAULT 'Active',
            created_at TEXT,
            updated_at TEXT,
            notes TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS customer_job_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_user_id INTEGER,
            customer_id INTEGER,
            created_by_username TEXT,
            status TEXT DEFAULT 'Submitted',
            priority TEXT DEFAULT 'Normal',
            request_title TEXT,
            service_type TEXT,
            property_address TEXT,
            requested_timeline TEXT,
            access_notes TEXT,
            description TEXT,
            photos_notes TEXT,
            customer_visible_notes TEXT,
            internal_notes TEXT,
            submitted_at TEXT,
            updated_at TEXT,
            reviewed_at TEXT,
            reviewed_by TEXT,
            converted_job_id INTEGER,
            request_ip TEXT,
            request_user_agent TEXT,
            FOREIGN KEY(customer_user_id) REFERENCES customer_user_profiles(id),
            FOREIGN KEY(customer_id) REFERENCES customers(id),
            FOREIGN KEY(converted_job_id) REFERENCES jobs(id)
        );
        CREATE TABLE IF NOT EXISTS customer_request_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            event_time TEXT,
            event_type TEXT,
            username TEXT,
            message TEXT,
            FOREIGN KEY(request_id) REFERENCES customer_job_requests(id)
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            job_name TEXT NOT NULL,
            address TEXT,
            scope TEXT,
            status TEXT DEFAULT 'Lead',
            price REAL DEFAULT 0,
            deposit REAL DEFAULT 0,
            paid REAL DEFAULT 0,
            payment_method TEXT,
            tax_status TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            category TEXT,
            vendor TEXT,
            description TEXT,
            amount REAL DEFAULT 0,
            paid_by TEXT,
            receipt_file TEXT,
            receipt_status TEXT,
            expense_date TEXT,
            created_at TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        );
        CREATE TABLE IF NOT EXISTS workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            default_rate REAL DEFAULT 140,
            classification TEXT DEFAULT 'Helper/Worker',
            notes TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS worker_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER,
            job_id INTEGER,
            work_date TEXT,
            description TEXT,
            amount REAL DEFAULT 0,
            payment_method TEXT,
            status TEXT DEFAULT 'Paid',
            notes TEXT,
            created_at TEXT,
            FOREIGN KEY(worker_id) REFERENCES workers(id),
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        );
        CREATE TABLE IF NOT EXISTS payroll_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_name TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT DEFAULT 'Open',
            total_worker_pay REAL DEFAULT 0,
            total_cost_fees REAL DEFAULT 0,
            total_hours REAL DEFAULT 0,
            created_at TEXT,
            closed_at TEXT,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS job_cost_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            snapshot_time TEXT,
            revenue REAL DEFAULT 0,
            deposits REAL DEFAULT 0,
            paid REAL DEFAULT 0,
            material_expenses REAL DEFAULT 0,
            worker_pay REAL DEFAULT 0,
            payroll_cost_fees REAL DEFAULT 0,
            owner_labor_value REAL DEFAULT 0,
            total_known_cost REAL DEFAULT 0,
            estimated_profit REAL DEFAULT 0,
            notes TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        );
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            invoice_number TEXT,
            invoice_type TEXT DEFAULT 'Invoice',
            issue_date TEXT,
            due_date TEXT,
            status TEXT DEFAULT 'Draft',
            subtotal REAL DEFAULT 0,
            deposit_due REAL DEFAULT 0,
            paid_amount REAL DEFAULT 0,
            balance_due REAL DEFAULT 0,
            payment_terms TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        );
        CREATE TABLE IF NOT EXISTS invoice_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER,
            job_id INTEGER,
            payment_date TEXT,
            amount REAL DEFAULT 0,
            method TEXT,
            reference TEXT,
            notes TEXT,
            created_at TEXT,
            FOREIGN KEY(invoice_id) REFERENCES invoices(id),
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        );
        CREATE TABLE IF NOT EXISTS bookkeeping_ledgers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_date TEXT,
            entry_type TEXT,
            category TEXT,
            job_id INTEGER,
            source_table TEXT,
            source_id INTEGER,
            description TEXT,
            debit REAL DEFAULT 0,
            credit REAL DEFAULT 0,
            status TEXT DEFAULT 'Open',
            receipt_status TEXT,
            created_at TEXT,
            updated_at TEXT,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS bookkeeping_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_name TEXT,
            match_text TEXT,
            category TEXT,
            entry_type TEXT,
            active INTEGER DEFAULT 1,
            notes TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS bookkeeping_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_time TEXT,
            run_type TEXT,
            total_income REAL DEFAULT 0,
            total_expenses REAL DEFAULT 0,
            total_worker_pay REAL DEFAULT 0,
            total_receivables REAL DEFAULT 0,
            unmatched_receipts INTEGER DEFAULT 0,
            missing_receipts INTEGER DEFAULT 0,
            duplicate_file_names INTEGER DEFAULT 0,
            open_jobs INTEGER DEFAULT 0,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS filekeeping_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_time TEXT,
            source_count INTEGER DEFAULT 0,
            indexed_files INTEGER DEFAULT 0,
            duplicate_file_names INTEGER DEFAULT 0,
            receipt_like_files INTEGER DEFAULT 0,
            missing_receipts INTEGER DEFAULT 0,
            inactive_sources INTEGER DEFAULT 0,
            missing_source_paths INTEGER DEFAULT 0,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS bookkeeping_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            alert_type TEXT,
            severity TEXT,
            title TEXT,
            message TEXT,
            related_table TEXT,
            related_id INTEGER,
            resolved INTEGER DEFAULT 0,
            resolved_at TEXT,
            resolved_by TEXT
        );
        CREATE TABLE IF NOT EXISTS owner_labor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            work_date TEXT,
            hours REAL DEFAULT 0,
            rate REAL DEFAULT 30,
            description TEXT,
            created_at TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        );
        CREATE TABLE IF NOT EXISTS owner_draws (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draw_date TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            paid_from_account TEXT DEFAULT 'Business checking',
            payment_method TEXT,
            description TEXT,
            work_type TEXT,
            job_id INTEGER,
            notes TEXT,
            source TEXT DEFAULT 'manual',
            created_at TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        );
        CREATE TABLE IF NOT EXISTS evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            file_path TEXT NOT NULL,
            file_type TEXT,
            description TEXT,
            added_at TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        );
        CREATE TABLE IF NOT EXISTS business_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_time TEXT,
            category TEXT,
            message TEXT,
            user_id INTEGER,
            username TEXT,
            session_id TEXT
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT,
            role TEXT DEFAULT 'viewer',
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            must_change_password INTEGER DEFAULT 1,
            created_at TEXT,
            last_login TEXT,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS online_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER,
            username TEXT,
            role TEXT,
            ip_address TEXT,
            user_agent TEXT,
            trusted_device_id TEXT,
            login_time TEXT,
            last_seen TEXT,
            active INTEGER DEFAULT 1,
            revoked INTEGER DEFAULT 0,
            revoke_reason TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS permissions_override (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            permission TEXT,
            allowed INTEGER DEFAULT 1,
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS file_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            source_type TEXT,
            folder_path TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS file_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER,
            file_path TEXT UNIQUE,
            file_name TEXT,
            extension TEXT,
            size INTEGER,
            modified_at TEXT,
            discovered_at TEXT,
            keywords TEXT,
            analysis TEXT,
            FOREIGN KEY(source_id) REFERENCES file_sources(id)
        );
        CREATE TABLE IF NOT EXISTS source_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER,
            summary_time TEXT,
            file_count INTEGER,
            total_size INTEGER,
            notes TEXT,
            FOREIGN KEY(source_id) REFERENCES file_sources(id)
        );
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS health_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time TEXT,
            level TEXT,
            component TEXT,
            message TEXT,
            fixed INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS troubleshooting_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_time TEXT,
            action TEXT,
            result TEXT,
            username TEXT
        );
        CREATE TABLE IF NOT EXISTS change_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            source TEXT,
            item_type TEXT,
            item_id TEXT,
            action TEXT,
            payload TEXT,
            applied INTEGER DEFAULT 0,
            applied_at TEXT,
            applied_by TEXT
        );
        CREATE TABLE IF NOT EXISTS data_refresh_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_time TEXT,
            run_type TEXT,
            source_count INTEGER DEFAULT 0,
            files_indexed INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0,
            errors INTEGER DEFAULT 0,
            notes TEXT,
            username TEXT
        );
        CREATE TABLE IF NOT EXISTS data_conflicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            detected_at TEXT,
            conflict_type TEXT,
            source_a TEXT,
            source_b TEXT,
            status TEXT DEFAULT 'Open',
            notes TEXT,
            resolved_at TEXT,
            resolved_by TEXT
        );
        CREATE TABLE IF NOT EXISTS cloud_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_name TEXT UNIQUE,
            host_type TEXT,
            base_url TEXT,
            status TEXT DEFAULT 'Planned',
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS record_locks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_type TEXT,
            record_id TEXT,
            locked_by_user_id INTEGER,
            locked_by_username TEXT,
            locked_at TEXT,
            expires_at TEXT,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS host_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time TEXT,
            level TEXT,
            host_mode TEXT,
            message TEXT,
            ip_address TEXT,
            username TEXT
        );
        CREATE TABLE IF NOT EXISTS shared_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_index_id INTEGER,
            file_path TEXT,
            file_name TEXT,
            shared_by_user_id INTEGER,
            shared_by_username TEXT,
            shared_with_role TEXT DEFAULT 'viewer',
            share_note TEXT,
            created_at TEXT,
            active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS shared_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            shared_by_user_id INTEGER,
            shared_by_username TEXT,
            shared_with_role TEXT DEFAULT 'viewer',
            share_note TEXT,
            created_at TEXT,
            active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS ai_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT,
            source_type TEXT,
            folder_path TEXT,
            api_enabled INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Configured',
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS mobile_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            device_label TEXT,
            device_token TEXT,
            last_seen TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS account_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requested_username TEXT UNIQUE NOT NULL,
            display_name TEXT,
            email TEXT,
            recovery_email TEXT,
            phone TEXT,
            address TEXT,
            worker_type TEXT,
            skills TEXT,
            emergency_contact TEXT,
            preferred_rate REAL DEFAULT 0,
            requested_role TEXT DEFAULT 'worker',
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            request_ip TEXT,
            request_user_agent TEXT,
            admin_notes TEXT,
            created_at TEXT,
            reviewed_at TEXT,
            reviewed_by TEXT
        );
        CREATE TABLE IF NOT EXISTS densus_access_grants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            request_note TEXT,
            admin_notes TEXT,
            request_ip TEXT,
            requested_at TEXT,
            reviewed_at TEXT,
            reviewed_by TEXT,
            last_download_at TEXT,
            UNIQUE(user_id)
        );
        CREATE TABLE IF NOT EXISTS worker_user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            username TEXT,
            display_name TEXT,
            email TEXT,
            phone TEXT,
            address TEXT,
            worker_type TEXT,
            skills TEXT,
            emergency_contact TEXT,
            preferred_rate REAL DEFAULT 0,
            account_request_id INTEGER,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS security_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time TEXT,
            level TEXT,
            event_type TEXT,
            username TEXT,
            ip_address TEXT,
            user_agent TEXT,
            message TEXT
        );
        CREATE TABLE IF NOT EXISTS account_request_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS known_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            device_fingerprint TEXT UNIQUE,
            device_label TEXT,
            device_kind TEXT DEFAULT 'browser',
            first_ip TEXT,
            last_ip TEXT,
            first_user_agent TEXT,
            last_user_agent TEXT,
            first_seen TEXT,
            last_seen TEXT,
            trust_status TEXT DEFAULT 'observed',
            approved_by TEXT,
            approved_at TEXT,
            blocked_by TEXT,
            blocked_at TEXT,
            last_verified_at TEXT,
            expires_at TEXT,
            remember_consent INTEGER DEFAULT 0,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS owner_recovery_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time TEXT,
            action TEXT,
            username TEXT,
            ip_address TEXT,
            user_agent TEXT,
            trusted_admin_device_id TEXT,
            result TEXT,
            notes TEXT
        );
        """)
        # Safe schema migrations for older installs. These do not overwrite data.
        for stmt in [
            "ALTER TABLE users ADD COLUMN email TEXT",
            "ALTER TABLE users ADD COLUMN recovery_email TEXT",
            "ALTER TABLE users ADD COLUMN phone TEXT",
            "ALTER TABLE users ADD COLUMN title TEXT",
            "ALTER TABLE users ADD COLUMN owner_account INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN last_profile_update TEXT",
            "ALTER TABLE users ADD COLUMN last_ip_address TEXT",
            "ALTER TABLE users ADD COLUMN last_user_agent TEXT",
            "ALTER TABLE online_sessions ADD COLUMN client_device_fingerprint TEXT",
            "ALTER TABLE online_sessions ADD COLUMN client_device_label TEXT",
            "ALTER TABLE online_sessions ADD COLUMN device_trust_status TEXT",
            "ALTER TABLE known_devices ADD COLUMN last_verified_at TEXT",
            "ALTER TABLE known_devices ADD COLUMN expires_at TEXT",
            "ALTER TABLE known_devices ADD COLUMN remember_consent INTEGER DEFAULT 0",
        ]:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        admin_row = conn.execute("SELECT id, active, role, salt, password_hash FROM users WHERE username=?", (DEFAULT_ADMIN_USERNAME,)).fetchone()
        if total_users == 0:
            # Local desktop first setup uses ivygrows/ivygrows (localhost only).
            # Cloud-primary/public deployments must use JRC_INITIAL_ADMIN_PASSWORD or create a locked owner account.
            if CLOUD_PRIMARY_MODE:
                if CLOUD_INITIAL_ADMIN_PASSWORD:
                    salt, ph = hash_password(CLOUD_INITIAL_ADMIN_PASSWORD)
                    conn.execute(
                        "INSERT INTO users (username, display_name, role, salt, password_hash, active, must_change_password, created_at, notes, email, recovery_email, phone, title, owner_account) VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?, ?, ?, ?, ?, 1)",
                        (DEFAULT_ADMIN_USERNAME, OWNER, "admin", salt, ph, now_iso(), "Cloud initial owner account created from JRC_INITIAL_ADMIN_PASSWORD. Must be changed after first login.", "enragementwow@hotmail.com", "enragementwow@hotmail.com", "(910) 712-0936", "Owner / Administrator")
                    )
                    conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("owner_setup_complete", "0"))
                    conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("admin_default_password_changed", "1"))
                    conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("cloud_initial_admin_password_used", "1"))
                else:
                    random_temp = secrets.token_urlsafe(32)
                    salt, ph = hash_password(random_temp)
                    conn.execute(
                        "INSERT INTO users (username, display_name, role, salt, password_hash, active, must_change_password, created_at, notes, email, recovery_email, phone, title, owner_account) VALUES (?, ?, ?, ?, ?, 0, 1, ?, ?, ?, ?, ?, ?, 1)",
                        (DEFAULT_ADMIN_USERNAME, OWNER, "admin", salt, ph, now_iso(), "Locked cloud owner placeholder. Set JRC_INITIAL_ADMIN_PASSWORD then redeploy, or use owner recovery from trusted local desktop.", "enragementwow@hotmail.com", "enragementwow@hotmail.com", "(910) 712-0936", "Owner / Administrator")
                    )
                    conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("owner_setup_complete", "0"))
                    conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("admin_default_password_changed", "1"))
                    conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("cloud_owner_locked_no_initial_password", "1"))
            else:
                salt, ph = hash_password(DEFAULT_ADMIN_PASSWORD)
                conn.execute(
                    "INSERT INTO users (username, display_name, role, salt, password_hash, active, must_change_password, created_at, notes, email, recovery_email, phone, title, owner_account) VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?, ?, ?, ?, ?, 1)",
                    (DEFAULT_ADMIN_USERNAME, OWNER, "admin", salt, ph, now_iso(), "Default local first-setup owner (ivygrows). Localhost only — must be changed before sharing access.", "enragementwow@hotmail.com", "enragementwow@hotmail.com", "(910) 712-0936", "Owner / Administrator")
                )
                conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("owner_setup_complete", "0"))
                conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("admin_default_password_changed", "0"))
        elif admin_row is None:
            # Existing database with no admin should never recreate admin/admin for remote/customer misuse.
            # Create a locked owner placeholder and require owner recovery from the trusted local PC.
            random_temp = secrets.token_urlsafe(24)
            salt, ph = hash_password(random_temp)
            conn.execute(
                "INSERT INTO users (username, display_name, role, salt, password_hash, active, must_change_password, created_at, notes, email, recovery_email, phone, title, owner_account) VALUES (?, ?, ?, ?, ?, 0, 1, ?, ?, ?, ?, ?, ?, 1)",
                (DEFAULT_ADMIN_USERNAME, OWNER, "admin", salt, ph, now_iso(), "Locked owner admin placeholder created because admin was missing. Use owner recovery on the trusted local PC.", "enragementwow@hotmail.com", "enragementwow@hotmail.com", "(910) 712-0936", "Owner / Administrator")
            )
        else:
            # Preserve the owner's changed password. Updates may restore active/role, but never reset the password to admin/admin.
            conn.execute("UPDATE users SET role='admin', owner_account=1, active=1 WHERE username=?", (DEFAULT_ADMIN_USERNAME,))
            conn.execute(
                "UPDATE users SET owner_account=0 WHERE username<>?",
                (DEFAULT_ADMIN_USERNAME,),
            )
            try:
                from app.first_setup_security import LEGACY_OWNER_USERNAMES
                for legacy in LEGACY_OWNER_USERNAMES:
                    if legacy.lower() != DEFAULT_ADMIN_USERNAME.lower():
                        conn.execute(
                            "UPDATE users SET active=0, owner_account=0, role='viewer' WHERE LOWER(username)=?",
                            (legacy.lower(),),
                        )
            except Exception:
                pass
            if not is_default_admin_password_active_conn(conn):
                conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("owner_setup_complete", "1"))
                conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("admin_default_password_changed", "1"))
        device_id = get_device_id()
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("trusted_admin_device_id", device_id))
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("owner", OWNER))
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("business_name", BUSINESS_NAME))
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("app_version", APP_VERSION))
        try:
            from app.host_laptop_roles import is_dedicated_host_install, ensure_host_admin_user
            if is_dedicated_host_install(BASE_DIR):
                ensure_host_admin_user(conn)
        except Exception:
            pass
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("recommended_host", "Cloud-primary live host with HTTPS and persistent data. Local desktop remains offline/admin companion only."))
        conn.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", ("std_business_name", "J & R Construction"))
        conn.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", ("std_business_phone", "(910) 712-0936"))
        conn.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", ("std_default_payment_terms", "50% deposit due before work begins. Remaining 50% balance due upon completion."))
        conn.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", ("std_customer_internal_rule", "Customer-facing documents must not include internal cost sheets, helper cost notes, profit notes, or tax-only notes."))
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("session_timeout_minutes", str(SESSION_TIMEOUT_MINUTES)))
        from app.schema_migrations import ensure_all_shared_schemas
        ensure_all_shared_schemas(conn)
        default_sources = [
            ("Program Evidence", "local", str(EVIDENCE_DIR)),
            ("Program Exports", "local", str(EXPORT_DIR)),
            ("ChatGPT Imports", "chatgpt", str(CHATGPT_IMPORTS_DIR)),
            ("Dropbox - Invoices2026 1.0", "dropbox-local", str(Path.home() / "Dropbox" / "Invoices2026 1.0")),
            ("Dropbox - J and R Construction", "dropbox-local", str(Path.home() / "Dropbox" / "J and R Construction")),
            ("Dropbox - JRC", "dropbox-local", str(Path.home() / "Dropbox" / "JRC")),
            ("Documents - JRC", "local", str(Path.home() / "Documents" / "JRC")),
        ]
        for label, stype, path in default_sources:
            row = conn.execute(
                "SELECT id FROM file_sources WHERE folder_path=? OR COALESCE(source_name, label)=? OR label=?",
                (path, label, label),
            ).fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO file_sources (label, source_name, source_type, folder_path, root_path, active, enabled, created_at) VALUES (?, ?, ?, ?, ?, 1, 1, ?)",
                    (label, label, stype, path, path, now_iso()),
                )
        conn.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", ("chatgpt_source_mode", "Import/export folder and optional API key only; private ChatGPT Business conversations are not directly readable."))
        conn.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", ("mobile_mode", "Browser/PWA mobile companion over the shared host URL."))
        conn.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", ("remote_mobile_policy", "Remote mobile access must use a secure tunnel/VPN or HTTPS cloud host. Do not expose the laptop directly to the public internet."))
        conn.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", ("remote_public_base_url", ""))
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("owner_notification_email", "enragementwow@hotmail.com"))
        conn.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", ("smtp_host", "smtp-mail.outlook.com"))
        conn.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", ("smtp_port", "587"))
        conn.execute("INSERT OR REPLACE INTO account_request_settings (key, value) VALUES (?, ?)", ("public_account_requests", "enabled"))
        conn.execute("INSERT OR REPLACE INTO account_request_settings (key, value) VALUES (?, ?)", ("default_requested_role", "worker"))
        conn.execute("INSERT OR REPLACE INTO account_request_settings (key, value) VALUES (?, ?)", ("approval_required", "true"))
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("owner_recovery_policy", "Transparent owner-only emergency recovery from trusted local host device; every use is logged."))
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("device_tracking_policy", "Users are identified by username, role, IP address, browser/device details, and a first-party remembered-device cookie only when the user checks the remember-this-device box. Remembered device consent expires after 90 days and must be verified again by login. No hidden access or device control is used."))
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("device_cookie_samesite", DEVICE_COOKIE_SAMESITE))
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("device_cookie_max_age_days", str(DEVICE_COOKIE_MAX_AGE_SECONDS // 86400)))
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("device_cookie_secure_policy", "Secure flag is used on HTTPS/public-host requests. Local LAN HTTP uses HttpOnly + SameSite + hashed server-side fingerprints so browser cookies continue to work."))
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("customer_portal_policy", "Customer accounts see only customer-facing request forms, their own submitted requests, and shared customer-visible items. They never see internal pricing notes, payroll, bookkeeping, other customers, or job-cost data."))
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("v6_business_structure", "Desktop office remains local/offline-first; cloud/tunnel/VPS is the correct structure for remote users; all dashboards route by verified login role; Dropbox is used as evidence/file-source storage, not as a live shared database."))
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("dropbox_file_source_policy", "Admins/managers may index local Dropbox-synced folders. Customers and non-company users can only see files intentionally shared through Shared Items, never the full file source explorer."))
        row = conn.execute("SELECT id FROM ai_sources WHERE label=?", ("ChatGPT Business Imports",)).fetchone()
        if not row:
            conn.execute("INSERT INTO ai_sources (label, source_type, folder_path, api_enabled, status, notes, created_at, updated_at) VALUES (?, ?, ?, 0, ?, ?, ?, ?)",
                         ("ChatGPT Business Imports", "chatgpt-import-folder", str(CHATGPT_IMPORTS_DIR), "Ready", "Place exported ChatGPT files here. Direct private ChatGPT Business sync is not available without a separate approved API/export workflow.", now_iso(), now_iso()))
        conn.execute(
            """
            UPDATE file_sources SET
                label = COALESCE(NULLIF(label, ''), source_name),
                source_name = COALESCE(NULLIF(source_name, ''), label),
                folder_path = COALESCE(NULLIF(folder_path, ''), root_path),
                root_path = COALESCE(NULLIF(root_path, ''), folder_path),
                active = COALESCE(active, enabled, 1),
                enabled = COALESCE(enabled, active, 1)
            """
        )
        try:
            from app.dropbox_business import ensure_dropbox_file_source
            dropbox_path = ensure_dropbox_file_source(conn)
            if dropbox_path:
                conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("dropbox_folder", dropbox_path))
        except Exception:
            pass
        for std_key, std_val in (
            ("std_owner_draw_rule", "When Jacob pays himself from business checking, log it as an owner draw (equity distribution), not as helper pay or a deductible expense."),
            ("std_owner_office_daily_rate", "170"),
            ("std_owner_draw_account", "Business checking"),
            ("std_owner_draw_work_type", "Business office full day"),
        ):
            conn.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (std_key, std_val))
        try:
            from app.owner_draws import ensure_owner_draws_schema, seed_july_2_2026_office_draw
            ensure_owner_draws_schema(conn)
            seed_july_2_2026_office_draw(conn)
        except Exception:
            pass
        conn.commit()

def log_event(category: str, message: str, level: str = "INFO") -> None:
    try:
        username = session.get("username") if session else None
        user_id = session.get("user_id") if session else None
        sid = session.get("sid") if session else None
    except Exception:
        username = user_id = sid = None
    try:
        conn = db() if hasattr(g, "db") else direct_db()
        conn.execute("INSERT INTO business_log (log_time, category, message, user_id, username, session_id) VALUES (?, ?, ?, ?, ?, ?)",
                     (now_iso(), category, message, user_id, username, sid))
        conn.commit()
    except Exception:
        pass
def health_event(level: str, component: str, message: str, fixed: int = 0) -> None:
    with direct_db() as conn:
        conn.execute("INSERT INTO health_events (event_time, level, component, message, fixed) VALUES (?, ?, ?, ?, ?)",
                     (now_iso(), level, component, message, fixed))
        conn.commit()
def host_event(level: str, host_mode: str, message: str) -> None:
    try:
        username = session.get("username") if session else None
        ip = request.remote_addr if request else None
    except Exception:
        username = None
        ip = None
    with direct_db() as conn:
        conn.execute("INSERT INTO host_events (event_time, level, host_mode, message, ip_address, username) VALUES (?, ?, ?, ?, ?, ?)",
                     (now_iso(), level, host_mode, message, ip, username))
        conn.commit()
def cleanup_stale_sessions() -> int:
    cutoff = (dt.datetime.now() - dt.timedelta(minutes=SESSION_TIMEOUT_MINUTES)).isoformat(timespec="seconds")
    with direct_db() as conn:
        cur = conn.execute("UPDATE online_sessions SET active=0, revoke_reason=? WHERE active=1 AND last_seen < ?",
                           (f"Auto-expired after {SESSION_TIMEOUT_MINUTES} minutes", cutoff))
        conn.commit()
        return cur.rowcount or 0
def get_user_permissions(user_id: int, role: str) -> set:
    perms = set(PERMISSIONS.get(normalize_role_for_session(role), set()))
    rows = db().execute("SELECT permission, allowed FROM permissions_override WHERE user_id=?", (user_id,)).fetchall()
    for row in rows:
        if row["allowed"]:
            perms.add(row["permission"])
        else:
            perms.discard(row["permission"])
    return perms
def current_user() -> Optional[sqlite3.Row]:
    uid = session.get("user_id")
    if not uid:
        return None
    row = db().execute("SELECT * FROM users WHERE id=? AND active=1", (uid,)).fetchone()
    return row


def session_densus_access() -> bool:
    user = current_user()
    if not user:
        return False
    try:
        from app.densus_access import has_densus_access

        return has_densus_access(db(), user["id"], user["username"], user["role"])
    except Exception:
        return is_admin_role(user["role"])


def touch_session() -> None:
    sid = session.get("sid")
    if sid:
        db().execute("UPDATE online_sessions SET last_seen=? WHERE session_id=?", (now_iso(), sid))
        db().commit()
def login_required(permission: Optional[str] = None, any_permission: Optional[Tuple[str, ...]] = None):
    def deco(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("login", next=request.path))
            sid = session.get("sid")
            cleanup_stale_sessions()
            if not sid:
                session.clear()
                flash("Your session expired. Please sign in again.", "warning")
                return redirect(url_for("login", next=request.path))
            row = db().execute("SELECT active, revoked FROM online_sessions WHERE session_id=?", (sid,)).fetchone()
            if not row or not row["active"] or row["revoked"]:
                session.clear()
                flash("Your session was ended by an administrator or expired.", "warning")
                return redirect(url_for("login"))
            touch_session()
            session["role"] = user["role"]
            if is_customer_or_external(user["role"]) and permission in {
                "view_admin", "manage_users", "manage_settings", "manage_devices",
                "owner_recovery", "configure_hosting", "configure_ai", "audit", "backup",
            }:
                abort(403)
            if int(user["must_change_password"] or 0) == 1 and request.endpoint not in {"change_password", "logout", "static"}:
                flash("Change the default/temporary password before using the program.", "warning")
                return redirect(url_for("change_password"))
            perms = get_user_permissions(user["id"], user["role"])
            if any_permission:
                if not any(p in perms for p in any_permission):
                    abort(403)
            elif permission and permission not in perms:
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return deco


def require_permission(permission: str) -> None:
    user = current_user()
    if not user:
        abort(403)
    perms = get_user_permissions(user["id"], user["role"])
    if permission not in perms:
        abort(403)
def get_app_setting(key: str, default: str = "") -> str:
    try:
        row = db().execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row and row["value"] is not None else default
    except Exception:
        return default
def set_app_setting(key: str, value: str) -> None:
    db().execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", (key, value or ""))
    db().commit()
def clean_base_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if value and not (value.startswith("https://") or value.startswith("http://")):
        value = "https://" + value
    return value
def access_url(base: str, path: str) -> str:
    return (base or "").rstrip("/") + path
def layout(title: str, body: str, active: str = "dashboard", *, public: bool = False) -> str:
    user = current_user()
    username = user["username"] if user else "Guest"
    role = user["role"] if user else ""
    perms = get_user_permissions(user["id"], user["role"]) if user else set()
    norm_role = normalize_role_for_session(role) if user else ""
    from app.dashboard_config import build_nav_items

    nav = build_nav_items(
        norm_role,
        perms,
        is_admin=is_admin_role(role),
        densus_access=session_densus_access() if user else False,
    )
    nav_html = "".join(
        f'<a class="nav {"on" if key==active else ""}" href="{href}">{label}</a>'
        for key, label, href, need in nav
        if public or need in perms or key in ("dashboard", "apply")
    )
    if not user and not public:
        nav_html = '<a class="nav on" href="/login">Sign In Required</a>'
    flash_html = "".join(f'<div class="flash {cat}">{html.escape(str(msg))}</div>' for cat, msg in get_flashed_messages_safe())
    srv_port = int(os.environ.get("JRC_PORT", "8765"))
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} - {APP_NAME}</title><link rel="manifest" href="/static/manifest.json"><meta name="theme-color" content="#84cc16"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="J&R Manager">
<style>
:root{{--bg:#000000;--panel:rgba(10,10,10,.92);--card:rgba(17,17,17,.85);--card-hover:rgba(30,30,30,.9);--glass-border:rgba(132,204,22,.22);--glass-border-light:rgba(163,230,53,.35);--soft:rgba(132,204,22,.08);--text:#f5f5f5;--muted:#a3a3a3;--accent:#84cc16;--accent2:#a3e635;--accent-glow:rgba(132,204,22,.4);--danger:#ef4444;--warn:#facc15;--gold:#bef264;--radius-sm:12px;--radius-md:18px;--radius-lg:24px;--radius-xl:28px;--blur:20px;--shadow:0 8px 32px rgba(0,0,0,.55);--shadow-glow:0 4px 24px rgba(132,204,22,.18)}}
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;color:var(--text);font-family:"Segoe UI",system-ui,-apple-system,sans-serif;background:var(--bg);background-image:radial-gradient(ellipse 80% 60% at 10% -10%,rgba(52,211,153,.18),transparent 55%),radial-gradient(ellipse 70% 50% at 95% 5%,rgba(96,165,250,.16),transparent 50%),radial-gradient(ellipse 60% 40% at 50% 100%,rgba(139,92,246,.1),transparent 55%),linear-gradient(160deg,#0a0f1c 0%,#111827 45%,#0c1222 100%);background-attachment:fixed}}
a{{color:var(--accent2);text-decoration:none;transition:color .2s ease}} a:hover{{color:#93c5fd}}
h1{{font-size:clamp(1.5rem,2.5vw,2rem);font-weight:800;margin:0 0 20px 0;letter-spacing:-.02em;background:linear-gradient(135deg,#fff 0%,#cbd5e1 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
h2{{font-size:1.15rem;font-weight:700;margin:0 0 12px 0;letter-spacing:-.01em}}
label{{display:block;font-size:13px;font-weight:600;color:#cbd5e1;margin-bottom:6px}}
.top{{display:flex;justify-content:space-between;align-items:center;padding:16px 24px;background:rgba(10,15,28,.72);backdrop-filter:blur(var(--blur));-webkit-backdrop-filter:blur(var(--blur));border-bottom:1px solid var(--glass-border);position:sticky;top:0;z-index:10;box-shadow:0 4px 24px rgba(0,0,0,.2)}}
.brand{{font-size:1.25rem;font-weight:800;color:#fff;letter-spacing:-.02em}} .sub{{color:var(--muted);font-size:12px;line-height:1.5}} .user{{text-align:right;color:var(--muted);font-size:13px;line-height:1.6}}
.wrap{{display:flex;min-height:calc(100vh - 64px)}} .side{{width:260px;background:rgba(10,15,28,.55);backdrop-filter:blur(var(--blur));-webkit-backdrop-filter:blur(var(--blur));border-right:1px solid var(--glass-border);padding:20px 14px}} .main{{flex:1;padding:24px 28px;max-width:1500px}}
.nav{{display:block;padding:11px 16px;border-radius:var(--radius-sm);color:#cbd5e1;margin:4px 0;border:1px solid transparent;transition:all .22s ease}} .nav:hover{{background:var(--soft);color:#fff;border-color:var(--glass-border);transform:translateX(2px)}} .nav.on{{background:linear-gradient(135deg,rgba(132,204,22,.22),rgba(163,230,53,.12));color:#fff;border-color:rgba(132,204,22,.45);box-shadow:var(--shadow-glow)}}
.card{{background:var(--card);backdrop-filter:blur(var(--blur));-webkit-backdrop-filter:blur(var(--blur));border:1px solid var(--glass-border);border-radius:var(--radius-lg);padding:22px;margin:0 0 20px 0;box-shadow:var(--shadow);transition:border-color .25s ease,box-shadow .25s ease,transform .25s ease}} .card:hover{{border-color:var(--glass-border-light);box-shadow:var(--shadow),var(--shadow-glow)}}
.card-narrow{{max-width:480px;margin-left:auto;margin-right:auto}} .card-wide{{max-width:780px;margin-left:auto;margin-right:auto}}
.glass-note{{display:flex;gap:12px;align-items:flex-start;background:rgba(255,255,255,.04);border:1px solid var(--glass-border);border-radius:var(--radius-md);padding:14px;backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:18px}} .stat{{background:rgba(255,255,255,.05);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border:1px solid var(--glass-border);border-radius:var(--radius-md);padding:18px;transition:transform .2s ease,border-color .2s ease}} .stat:hover{{transform:translateY(-2px);border-color:var(--glass-border-light)}}
.stat b{{display:block;font-size:1.6rem;color:#fff;margin-top:6px;font-weight:800;letter-spacing:-.02em}} .muted{{color:var(--muted);line-height:1.55}}
input,select,textarea{{background:rgba(15,23,42,.65);border:1px solid var(--glass-border);color:var(--text);border-radius:var(--radius-sm);padding:11px 14px;width:100%;font:inherit;transition:border-color .2s ease,box-shadow .2s ease,background .2s ease}} input:focus,select:focus,textarea:focus{{outline:none;border-color:rgba(132,204,22,.65);box-shadow:0 0 0 3px rgba(132,204,22,.18);background:rgba(10,10,10,.95)}} textarea{{min-height:96px;resize:vertical}}
input[type=checkbox]{{width:auto;accent-color:var(--accent)}}
button,.btn{{background:linear-gradient(135deg,#84cc16,#65a30d);color:#000;border:1px solid rgba(163,230,53,.35);border-radius:var(--radius-sm);padding:11px 18px;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;min-height:44px;line-height:1.15;text-align:center;white-space:normal;box-shadow:0 4px 16px rgba(132,204,22,.28);transition:transform .18s ease,box-shadow .18s ease,filter .18s ease}} button:hover,.btn:hover{{transform:translateY(-1px);box-shadow:0 6px 22px rgba(132,204,22,.4);filter:brightness(1.06)}}
.btn2{{background:rgba(255,255,255,.08);color:#e2e8f0;border-color:var(--glass-border);box-shadow:none}} .btn2:hover{{background:rgba(255,255,255,.12);box-shadow:0 4px 16px rgba(0,0,0,.2)}}
.danger{{background:linear-gradient(135deg,#f87171,#ef4444);color:#fff;border-color:rgba(255,255,255,.12);box-shadow:0 4px 16px rgba(248,113,113,.25)}} .warn{{background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#1c1917;border-color:rgba(255,255,255,.12);box-shadow:0 4px 16px rgba(251,191,36,.2)}}
.action-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:14px}} .action-grid .btn{{width:100%;min-height:50px;border-radius:var(--radius-md)}} .dashboard-note{{font-size:13px;color:#a5b4fc;margin-top:8px}}
table{{width:100%;border-collapse:separate;border-spacing:0;background:rgba(255,255,255,.03);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border:1px solid var(--glass-border);border-radius:var(--radius-md);overflow:hidden}} th,td{{padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.06);text-align:left;vertical-align:top}} th{{color:#f8fafc;background:rgba(255,255,255,.05);font-size:12px;text-transform:uppercase;letter-spacing:.04em;font-weight:700}} tr:last-child td{{border-bottom:0}} tbody tr{{transition:background .15s ease}} tbody tr:hover{{background:rgba(255,255,255,.04)}}
.row{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}} .row3{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}} form p{{margin:0 0 14px 0}}
.flash{{padding:14px 16px;border-radius:var(--radius-sm);margin-bottom:14px;background:rgba(52,211,153,.12);border:1px solid rgba(52,211,153,.35);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)}} .flash.warning{{background:rgba(251,191,36,.12);border-color:rgba(251,191,36,.35)}} .flash.error{{background:rgba(248,113,113,.12);border-color:rgba(248,113,113,.35)}}
.badge{{display:inline-block;padding:5px 10px;border-radius:999px;background:rgba(255,255,255,.06);border:1px solid var(--glass-border);color:#e2e8f0;font-size:12px;font-weight:600}} .ok{{background:rgba(132,204,22,.18);border-color:rgba(132,204,22,.4);color:#bef264}} .red{{background:rgba(248,113,113,.15);border-color:rgba(248,113,113,.35);color:#fca5a5}} .yellow{{background:rgba(251,191,36,.15);border-color:rgba(251,191,36,.35);color:#fde68a}} .pill{{display:inline-block;padding:2px 8px;border-radius:999px;background:rgba(132,204,22,.2);color:#bef264;font-size:11px;font-weight:700;margin-left:6px}}
.side hr{{border:0;border-top:1px solid var(--glass-border);margin:16px 0}}
.footer{{color:var(--muted);font-size:12px;margin-top:32px;padding-top:16px;border-top:1px solid var(--glass-border);line-height:1.6}}
::-webkit-scrollbar{{width:10px;height:10px}} ::-webkit-scrollbar-track{{background:rgba(255,255,255,.03)}} ::-webkit-scrollbar-thumb{{background:rgba(255,255,255,.15);border-radius:999px;border:2px solid transparent;background-clip:padding-box}} ::-webkit-scrollbar-thumb:hover{{background:rgba(255,255,255,.25)}}
@media(max-width:850px){{.top{{display:block;padding:14px 16px}}.user{{text-align:left;margin-top:10px}}.wrap{{display:block}}.side{{width:auto;display:flex;gap:8px;overflow-x:auto;padding:12px;border-right:0;border-bottom:1px solid var(--glass-border)}}.nav{{white-space:nowrap;margin:0;flex:0 0 auto}}.main{{padding:16px}}.row,.row3{{grid-template-columns:1fr}}.grid{{grid-template-columns:1fr}}.action-grid{{grid-template-columns:1fr}}table{{display:block;overflow-x:auto}}.card{{border-radius:var(--radius-md);padding:16px}}h1{{font-size:1.45rem}}.mobile-actions .btn,.action-grid .btn{{display:flex;margin:6px 0;text-align:center}}}}
</style></head><body>
<div class="top"><div><div class="brand">{APP_NAME}</div><div class="sub">Owned and operated by {OWNER} / {BUSINESS_NAME} • {PHONE} • v{APP_VERSION}</div></div><div class="user">{html.escape(username)} {html.escape(role_display(role))}<br><a href="/logout">Logout</a></div></div>
<div class="wrap"><aside class="side">{nav_html}<hr><div class="sub">Server: {html.escape(get_lan_ip())}:{srv_port}<br>Trusted PC: {html.escape(platform.node())}</div></aside><main class="main">{flash_html}<h1>{html.escape(title)}</h1>{body}<div class="footer">Use on trusted LAN/VPN or properly secured cloud host only. Always use strong passwords and HTTPS for remote access.</div></main></div></body></html>"""
def get_flashed_messages_safe():
    try:
        from flask import get_flashed_messages
        return get_flashed_messages(with_categories=True)
    except Exception:
        return []
app = Flask(__name__)
TRUSTED_HOSTS_ENV = os.environ.get("JRC_TRUSTED_HOSTS", "").strip()
if TRUSTED_HOSTS_ENV:
    app.config["TRUSTED_HOSTS"] = [h.strip() for h in TRUSTED_HOSTS_ENV.split(",") if h.strip()]
# Local install should not force host-header validation; cloud deployments can set JRC_TRUSTED_HOSTS.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=PUBLIC_HOST_MODE,
    PERMANENT_SESSION_LIFETIME=dt.timedelta(minutes=SESSION_TIMEOUT_MINUTES),
    MAX_CONTENT_LENGTH=200 * 1024 * 1024,
)

@app.before_request
def enforce_global_login_required():
    """Every user including admin must sign in before any program page."""
    from app.auth_gate import enforce_web_login_gate

    resp = enforce_web_login_gate(session, lambda nxt: redirect(url_for("login", next=nxt)))
    if resp is not None:
        return resp


@app.before_request
def protect_admin_and_sensitive_surfaces():
    """Block customers/external users and non-admins from admin-only URLs."""
    path = request.path or ""
    if not path or path.startswith("/static") or path in {"/login", "/logout", "/connect", "/mobile/ping", "/register", "/apply", "/emergency-access"}:
        return
    role = session.get("role", "")
    if session.get("user_id") and is_customer_or_external(role):
        blocked = (
            "/admin", "/hosting", "/cloud", "/owner-recovery", "/data", "/ai",
            "/payroll", "/expenses", "/bookkeeping", "/job-costs", "/owner-draws", "/jobs", "/files",
            "/business", "/invoices", "/applications", "/customers", "/filekeeping",
        )
        if any(path.startswith(p) for p in blocked):
            forbid_customer_external_admin_surface()
    if session.get("user_id") and path.startswith("/admin") and not has_permission_role(role, "view_admin"):
        abort(403)

@app.after_request
def set_security_headers(resp):
    sensitive_prefixes = ("/admin", "/hosting", "/cloud", "/owner-recovery", "/payroll", "/expenses", "/bookkeeping", "/job-costs", "/owner-draws", "/files", "/applications", "/customers")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    resp.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; frame-ancestors 'self'")
    resp.headers.setdefault("Cache-Control", "no-store" if request.path.startswith(sensitive_prefixes) else "private, max-age=30")
    if PUBLIC_HOST_MODE:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp
# Prefer an environment secret for cloud/hosted mode so restarts keep sessions stable
# without writing secrets into deploy images. Local desktop installs keep the existing
# per-install secret file for offline use.
env_secret = os.environ.get("JRC_SECRET_KEY", "").strip()
if env_secret:
    app.secret_key = env_secret
elif SERVER_SECRET_PATH.exists():
    app.secret_key = SERVER_SECRET_PATH.read_text(encoding="utf-8").strip()
else:
    secret = secrets.token_hex(32)
    SERVER_SECRET_PATH.write_text(secret, encoding="utf-8")
    app.secret_key = secret
@app.teardown_appcontext
def close_db(exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()
@app.route("/setup-status")
@login_required("audit")
def setup_status_page():
    body = """
    <div class='card'><h2>Setup / Verification Center</h2>
    <p>This page is for owner/admin setup after install. Installers do not collect passwords; login happens inside this secured app.</p>
    <p>
      <a class='btn' href='/health'>System Check</a>
      <a class='btn btn2' href='/security-audit'>Security Audit</a>
      <a class='btn btn2' href='/owner-security-status'>Owner Security Status</a>
      <a class='btn btn2' href='/cloud-status'>Cloud Status</a>
      <a class='btn btn2' href='/admin/troubleshooter'>Full Troubleshooter</a>
    </p>
    <p><a class='btn btn2' href='/api/live/ready'>Live Readiness API</a>
    <a class='btn btn2' href='/connect'>Connection Test</a></p>
    <ul><li>Use a strong admin password.</li><li>Use HTTPS for cloud/internet users.</li><li>Set JRC_SECRET_KEY and JRC_TRUSTED_HOSTS in cloud hosting.</li><li>Use customer and external roles for outside users.</li></ul>
    </div>
    """
    return layout("Setup / Verification Center", body, "health")


@app.route("/setup")
@login_required("audit")
def setup_redirect():
    """Legacy alias — dashboard and setup-complete linked /setup before /setup-status existed."""
    return redirect(url_for("setup_status_page"))
@app.route("/cloud-status")
@login_required("configure_hosting")
def cloud_status_page():
    cloud_base = os.environ.get("JRC_CLOUD_BASE_URL", "")
    db_exists = DB_PATH.exists()
    body = f"""
    <div class='card'><h2>Cloud / Remote Business Structure</h2>
    <p>This page shows whether the program is ready for real remote access. Local laptop hosting is for same-Wi-Fi/VPN testing. Cloud/tunnel/VPS hosting is the stable option for customers, workers, managers, and non-company users outside your location.</p>
    <table>
      <tr><th>Check</th><th>Status</th></tr>
      <tr><td>Public host mode</td><td>{'ON' if PUBLIC_HOST_MODE else 'OFF - local/desktop mode'}</td></tr>
      <tr><td>Database file</td><td>{'FOUND' if db_exists else 'MISSING until first install/open'}</td></tr>
      <tr><td>Cloud base URL env</td><td>{html.escape(cloud_base or 'not set')}</td></tr>
      <tr><td>HTTPS request detected</td><td>{'YES' if is_https_request() else 'NO / local HTTP'}</td></tr>
      <tr><td>Secure cookie mode</td><td>{'Secure flag ON' if cookie_secure_flag() else 'Local HTTP mode: HttpOnly + SameSite + server-side token hashing'}</td></tr>
    </table>
    </div>
    <div class='card'><h2>Recommended J&R Live Server Pattern</h2>
    <ol><li>Primary recommendation: Render paid web service with persistent disk and HTTP health check.</li><li>Use Railway/Fly.io as alternatives if you prefer those dashboards.</li><li>Use Cloudflare Tunnel only as a self-host fallback, not router port forwarding.</li><li>Use HTTPS, JRC_SECRET_KEY, JRC_TRUSTED_HOSTS, JRC_CLOUD_BASE_URL, and JRC_INITIAL_ADMIN_PASSWORD.</li><li>Store live data in persistent JRC_DATA_DIR and back up before every deploy.</li></ol>
    <p><a class='btn' href='/api/cloud/status'>Open Cloud Status API</a> <a class='btn btn2' href='/connect'>Connection Test</a></p></div>
    """
    return layout("Cloud Status", body, "cloud")
@app.route("/api/cloud/status")
def api_cloud_status():
    return jsonify({
        "ok": True,
        "app": APP_NAME,
        "version": APP_VERSION,
        "public_host_mode": PUBLIC_HOST_MODE,
        "https_detected": is_https_request(),
        "secure_cookie_flag": cookie_secure_flag(),
        "database_present": DB_PATH.exists(),
        "roles": ROLE_LABELS,
        "customer_portal": True,
        "non_company_minimal_access": True,
        "trusted_hosts_configured": bool(os.environ.get("JRC_TRUSTED_HOSTS", "").strip()),
        "secret_from_environment": bool(os.environ.get("JRC_SECRET_KEY", "").strip()),
        "timestamp": now_iso(),
    })

@app.route("/api/cloud/primary-status")
def api_cloud_primary_status():
    return jsonify({
        "ok": True,
        "cloud_primary_mode": CLOUD_PRIMARY_MODE,
        "data_dir": str(DATA_DIR),
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "initial_admin_password_env_set": bool(CLOUD_INITIAL_ADMIN_PASSWORD),
        "public_host_mode": PUBLIC_HOST_MODE,
        "trusted_hosts_configured": bool(os.environ.get("JRC_TRUSTED_HOSTS", "").strip()),
        "cloud_base_url": os.environ.get("JRC_CLOUD_BASE_URL", ""),
        "message": "Cloud-primary deployments should set JRC_DATA_DIR to persistent storage and JRC_INITIAL_ADMIN_PASSWORD for first owner login."
    })

@app.route("/api/live/ready")
def api_live_ready():
    """Cloud load balancer and admin readiness check.
    Returns 200 only when core app, database, data directory, and role system are ready.
    """
    status = {
        "ok": True,
        "app": APP_NAME,
        "version": APP_VERSION,
        "mode": "cloud-primary" if CLOUD_PRIMARY_MODE else "local-office",
        "public_host_mode": PUBLIC_HOST_MODE,
        "data_dir": str(DATA_DIR),
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "https_detected": is_https_request(),
        "secure_cookie_flag": cookie_secure_flag(),
        "roles": ROLE_LABELS,
        "cloud_base_url": os.environ.get("JRC_CLOUD_BASE_URL", ""),
        "trusted_hosts_configured": bool(os.environ.get("JRC_TRUSTED_HOSTS", "").strip()),
        "secret_from_environment": bool(os.environ.get("JRC_SECRET_KEY", "").strip()),
        "initial_admin_env_set": bool(CLOUD_INITIAL_ADMIN_PASSWORD),
        "timestamp": now_iso(),
    }
    try:
        conn = direct_db()
        row = conn.execute("SELECT 1 AS ok").fetchone()
        status["database_query_ok"] = bool(row)
        status["db_schema_core_ok"] = all(table_exists(conn, t) for t in ["users", "jobs", "customer_job_requests", "file_sources"])
        conn.close()
    except Exception as exc:
        status["ok"] = False
        status["database_error"] = str(exc)
    return jsonify(status), (200 if status.get("ok") else 500)

@app.route("/primary-live-readiness")
@login_required("configure_hosting")
def primary_live_readiness_page():
    body = """
    <div class='card'><h2>Primary Live Reliable Business Server</h2>
    <p>This page is for the final J&R cloud/server setup. The recommended structure is a paid always-on cloud web service with persistent disk/storage, health checks, HTTPS, and environment secrets. Local router hosting is not recommended for customers or workers.</p>
    <div class='grid'>
      <div class='stat'>Best Simple Live Option<b>Render Web Service + Persistent Disk</b><span class='muted'>Use included render.yaml, health check, and /var/data/jrc persistent data.</span></div>
      <div class='stat'>Alternative<b>Railway or Fly.io</b><span class='muted'>Use included configs; keep at least one instance running.</span></div>
      <div class='stat'>Self-host fallback<b>Cloudflare Tunnel</b><span class='muted'>Better than router port forwarding; outbound-only tunnel.</span></div>
    </div>
    <p><a class='btn' href='/api/live/ready'>Open Live Readiness API</a> <a class='btn btn2' href='/cloud-status'>Cloud Status</a> <a class='btn btn2' href='/cloud'>Cloud Setup</a></p>
    <ul><li>Set JRC_SECRET_KEY, JRC_INITIAL_ADMIN_PASSWORD, JRC_TRUSTED_HOSTS, and JRC_CLOUD_BASE_URL before live use.</li><li>Use HTTPS for customers/workers.</li><li>Keep all live data under persistent JRC_DATA_DIR.</li><li>Run Primary Live Server Check after deployment.</li></ul>
    </div>
    """
    return layout("Primary Live Readiness", body, "cloud")


@app.route("/login-start")
def login_start():
    """Simple separated landing page: login first, dashboard second."""
    init_db()
    body = """
    <div class='card'><h2>Login First</h2>
      <p>Use this page before opening any dashboard. The installer does not collect passwords; login happens here inside the secured app.</p>
      <p><a class='btn' href='/login'>Open Login Screen</a> <a class='btn btn2' href='/setup-status'>Setup Status</a></p>
      <p class='muted'>Default first setup account: <b>ivygrows / ivygrows</b> (localhost only). Change it after you sign in.</p>
    </div>
    <div class='card'><h2>Dashboard After Login</h2><p>After successful login, JRC Manager sends each account to the right dashboard: owner/admin, manager, worker, viewer, customer, or non-company external.</p></div>
    """
    return layout("Login First", body, "")

@app.route("/login", methods=["GET", "POST"])
def login():
    init_db()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db().execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
        remember_device = request.form.get("remember_device") == "1"
        existing_token = get_client_device_token()
        token = existing_token or (make_client_device_token() if remember_device else "")
        if token and is_client_device_blocked(token):
            log_security_event("login_blocked_device", username, "Blocked remembered device attempted login", "WARN")
            flash("This device has been blocked by an administrator.", "error")
            return redirect(url_for("login"))
        if user and verify_password(password, user["salt"], user["password_hash"]):
            # Default ivygrows/ivygrows is LOCALHOST first-setup only — never LAN/remote/cloud.
            if username == DEFAULT_ADMIN_USERNAME and password == DEFAULT_ADMIN_PASSWORD and is_default_admin_password_active():
                if PUBLIC_HOST_MODE or not is_local_setup_request() or not ALLOW_LOCAL_DEFAULT_ADMIN:
                    log_security_event("default_admin_remote_blocked", username, "Blocked non-localhost attempt to use first-setup owner login", "ERROR")
                    flash("First-setup owner login works only on this PC at localhost during initial setup. Use your changed password or emergency mastery access.", "error")
                    return redirect(url_for("login"))
            sid = str(uuid.uuid4())
            ua = request.headers.get("User-Agent", "")
            trust_status = record_known_device(user["id"], user["username"], token, ua, remember_device)
            fingerprint = _hash_device_token(token) if token and remember_device else ""
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            normalized_role = normalize_role_for_session(user["role"])
            session["role"] = normalized_role
            session["sid"] = sid
            db().execute("UPDATE users SET last_login=?, last_ip_address=?, last_user_agent=? WHERE id=?", (now_iso(), client_ip(), ua, user["id"]))
            db().execute("INSERT INTO online_sessions (session_id,user_id,username,role,ip_address,user_agent,trusted_device_id,client_device_fingerprint,client_device_label,device_trust_status,login_time,last_seen,active) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)",
                         (sid, user["id"], user["username"], normalized_role, client_ip(), ua, get_device_id(), fingerprint, client_device_label(ua), trust_status, now_iso(), now_iso()))
            if normalized_role != (user["role"] or ""):
                db().execute("UPDATE users SET role=? WHERE id=?", (normalized_role, user["id"]))
            db().commit()
            try:
                from app.master_owner import register_master_owner_device, owner_login_trust_level
                register_master_owner_device(user["username"], db())
                trust = owner_login_trust_level(user["username"], client_ip())
                log_security_event("owner_login_trust", username, f"Admin login trust level: {trust}", "OK" if trust == "master" else "INFO")
            except Exception:
                pass
            log_event("Login", f"User {username} logged in from {client_ip()} on {client_device_label(ua)}"); log_security_event("login_success", username, f"Login successful; device {trust_status}", "OK")
            try:
                from app.auth_gate import record_pc_verification
                record_pc_verification(db(), user["id"], username, client_ip(), ua)
            except Exception:
                pass
            if username == DEFAULT_ADMIN_USERNAME and password == DEFAULT_ADMIN_PASSWORD and is_default_admin_password_active():
                flash("First-setup login active (ivygrows / ivygrows). Change this password now before sharing access.", "warning")
            resp = redirect(request.args.get("next") or url_for("setup_complete"))
            if remember_device and token:
                set_secure_device_cookie(resp, token)
            else:
                clear_device_cookie(resp)
            return resp
        pending = db().execute(
            "SELECT * FROM account_requests WHERE requested_username=? AND status='Pending'",
            (username,),
        ).fetchone()
        if pending and verify_password(password, pending["salt"], pending["password_hash"]):
            log_security_event(
                "login_pending_approval",
                username,
                "Login blocked — account request pending owner/admin approval",
                "INFO",
            )
            flash(
                "Your account request is waiting for owner/admin approval. "
                "You will receive an email when it is approved or denied.",
                "warning",
            )
            return redirect(url_for("login"))
        denied = db().execute(
            "SELECT salt, password_hash, status FROM account_requests WHERE requested_username=? ORDER BY id DESC LIMIT 1",
            (username,),
        ).fetchone()
        if (
            denied
            and denied["status"] == "Denied"
            and verify_password(password, denied["salt"], denied["password_hash"])
        ):
            log_security_event("login_denied_request", username, "Login blocked — account request was denied", "WARN")
            flash(
                "Your account request was denied by the owner/admin. Contact J & R Construction if you need access.",
                "error",
            )
            return redirect(url_for("login"))
        log_security_event("login_failed", username, "Invalid login or inactive account", "WARN")
        flash("Invalid login or inactive account.", "error")
    body = """
    <div class="card card-narrow">
      <h2>Sign in</h2>
      <form method="post">
        <p><label>Username</label><input name="username" autocomplete="username" autofocus></p>
        <p><label>Password</label><input name="password" type="password" autocomplete="current-password"></p>
        <p class="glass-note">
          <input name="remember_device" value="1" type="checkbox" style="margin-top:4px">
          <span><b>Remember this PC/phone for 90 days</b><br><span class="muted">Only check this on your own trusted device. You still log in normally, but the device is recognized for security and admin review. After 90 days, you must verify again by logging in and checking this box.</span></span>
        </p>
        <button>Login</button>
      </form>
      <p class="muted">After login, the program automatically opens the correct dashboard for your account type: owner/admin, manager, worker, viewer, customer, or non-company external user.</p>
      <p class="muted">First-time owner setup (this PC only): <b>ivygrows / ivygrows</b>. Change it immediately after login.</p>
      <p><a class="btn btn2" href="/apply">Apply for work (full employee application)</a></p>
      <p><a class="btn btn2" href="/register">Request login account</a></p>
      <p><a class="btn btn2" href="/owner-recovery">Owner emergency recovery</a></p>
      <p><a class="btn btn2" href="/emergency-access">Emergency owner access (mastery key)</a></p>
      <p class="muted">Sign-in is required for every user before any dashboard, jobs, or admin tools. Public pages: login, register, apply, emergency access only.</p>
    </div>"""
    return layout("Login", body, "", public=True)
@app.route("/register", methods=["GET", "POST"])
def public_account_request():
    init_db()
    if get_app_setting("public_account_requests", "enabled") != "enabled":
        body = """<div class='card card-wide'><h2>Account Requests Paused</h2>
        <p class='muted'>Public account requests are temporarily disabled by the administrator. Contact Jacob / J &amp; R Construction to request access.</p>
        <p><a class='btn' href='/login'>Back to login</a></p></div>"""
        return layout("Request Access", body, "")
    if request.method == "POST":
        ip = client_ip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        display_name = request.form.get("display_name", "").strip()
        role = request.form.get("requested_role", "guest")
        allowed_register = {"worker", "helper", "subcontractor", "viewer", "guest", "non_company", "customer"}
        if role not in allowed_register:
            role = "guest"
        ok_pw, pw_msg = password_quality(password)
        if request_rate_limited(ip):
            log_security_event("account_request_rate_limit", username, "Too many account requests from this IP", "WARN")
            flash("Too many account requests from this connection today. Ask Jacob/admin to add the account manually.", "error")
        elif not username or not password or not display_name:
            flash("Name, username, and password are required.", "error")
        elif not (request.form.get("email") or "").strip():
            flash("Email is required so we can notify you when the owner approves or denies your request.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif not ok_pw:
            flash(pw_msg, "error")
        elif db().execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
            flash("That username already exists. Choose another username or ask Jacob to reset it.", "error")
        elif db().execute("SELECT id FROM account_requests WHERE requested_username=? AND status='Pending'", (username,)).fetchone():
            flash("That username already has a pending request.", "warning")
        else:
            salt, ph = hash_password(password)
            conn = db()
            cur = conn.execute("""INSERT INTO account_requests
                (requested_username, display_name, email, recovery_email, phone, address, worker_type, skills, emergency_contact, preferred_rate, requested_role, salt, password_hash, status, request_ip, request_user_agent, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (username, display_name, request.form.get("email"), request.form.get("recovery_email"), request.form.get("phone"), request.form.get("address"), request.form.get("worker_type"), request.form.get("skills"), request.form.get("emergency_contact"), parse_float(request.form.get("preferred_rate")), role, salt, ph, "Pending", ip, request.headers.get("User-Agent", ""), now_iso()))
            req_id = int(cur.lastrowid)
            conn.commit()
            log_event("Account Request", f"New account request #{req_id} for {username} from {ip} — pending owner approval")
            log_security_event("account_request_created", username, f"Requested role: {role}; owner approval required", "INFO")
            try:
                from app.application_notifications import ensure_account_request_notification_columns, notify_owner_new_account_request

                ensure_account_request_notification_columns(conn)
                ok, note = notify_owner_new_account_request(conn, req_id, request_base_url=request.url_root.rstrip("/"))
                log_event("Account Request", f"Owner notified for request #{req_id}: {note}")
            except Exception as exc:
                log_event("Account Request", f"Owner notify error request #{req_id}: {exc}")
            body = f"""
            <div class='card card-wide'><h2>Request Sent — Owner Approval Required</h2>
            <p>Your account request <b>#{req_id}</b> was saved. <b>Jacob / owner-admin must approve</b> before you can sign in.</p>
            <p class='muted'>You will receive an email at {html.escape((request.form.get('email') or '').strip())} when your request is approved or denied.</p>
            <p><a class='btn' href='/login'>Back to login</a></p></div>"""
            return layout("Account Request Sent", body, "", public=True)
    body = """
    <div class='card card-wide'>
      <h2>Request J&R Manager Access</h2>
      <p class='muted'>Use this form from a phone or computer. No install needed. <b>Owner/admin must approve</b> every request before login works. You will be emailed when approved or denied.</p>
      <form method='post'>
        <div class='row'><p><label>Full Name</label><input name='display_name' required></p><p><label>Desired Username</label><input name='username' required></p></div>
        <div class='row'><p><label>Password</label><input name='password' type='password' required placeholder='Min 8 chars, upper/lower/number'></p><p><label>Confirm Password</label><input name='confirm_password' type='password' required></p></div>
        <div class='row3'><p><label>Email (required)</label><input name='email' type='email' required placeholder='Status updates sent here'></p><p><label>Recovery Email</label><input name='recovery_email' type='email'></p><p><label>Phone</label><input name='phone'></p></div>
        <p><label>Address</label><input name='address'></p>
        <div class='row3'><p><label>Worker Type / Relationship</label><input name='worker_type' placeholder='Helper, subcontractor, customer'></p><p><label>Preferred Rate</label><input name='preferred_rate' placeholder='140'></p><p><label>Requested Access</label><select name='requested_role'>
          <option value='guest'>Guest / applicant (minimal until approved)</option>
          <option value='helper'>Field helper</option>
          <option value='worker'>Company employee</option>
          <option value='subcontractor'>Subcontractor (1099)</option>
          <option value='viewer'>Read-only staff</option>
          <option value='non_company'>External contact</option>
          <option value='customer'>Customer portal</option>
        </select></p></div>
        <p class='muted'>For full hire onboarding (insurance, W-9, work history), use <a href='/apply'>Apply for Work</a> instead.</p>
        <p><label>Skills / Job Role</label><textarea name='skills' placeholder='Carpentry, painting, helper, office, photo uploads, etc.'></textarea></p>
        <p><label>Emergency Contact / Notes</label><textarea name='emergency_contact'></textarea></p>
        <button>Submit Account Request</button> <a class='btn btn2' href='/login'>Cancel</a> <a class='btn btn2' href='/apply'>Full job application</a>
      </form>
    </div>"""
    return layout("Request Access", body, "", public=True)
@app.route("/logout")
def logout():
    sid = session.get("sid")
    if sid:
        db().execute("UPDATE online_sessions SET active=0,last_seen=? WHERE session_id=?", (now_iso(), sid))
        db().commit()
    session.clear()
    return redirect(url_for("login"))
def role_command_center(role: str, perms: set[str]) -> str:
    """Clean role-specific dashboard action center.

    Uses button grids instead of inline buttons so dashboard actions appear correctly
    on desktop, tablets, and phones. Every action shown is role appropriate.
    """
    role = normalize_role_for_session(role or "viewer")
    def grid(title, note, actions):
        buttons = "".join(f"<a class='btn {cls}' href='{href}'>{label}</a>" for label, href, cls in actions)
        return f"""
        <div class='card'><h2>{title}</h2><p class='muted'>{note}</p><div class='action-grid'>{buttons}</div></div>
        """
    if role == "admin":
        return grid("Owner Command Center", "Daily order: requests, active jobs, money, files, users, then verification tools only when needed.", [
            ("Jobs", "/jobs", ""), ("Customer Requests", "/customers/requests", "btn2"),
            ("Worker Applications", "/applications", "btn2"), ("Job Costs", "/job-costs", "btn2"),
            ("Files", "/files", "btn2"), ("Users / Admin", "/admin", "btn2"),
        ])
    if role == "manager":
        return grid("Manager Command Center", "Manage daily operations without owner-only security and deployment tools.", [
            ("Jobs", "/jobs", ""), ("Customer Requests", "/customers/requests", "btn2"),
            ("Applications", "/applications", "btn2"), ("Payroll", "/payroll", "btn2"),
            ("Files", "/files", "btn2"), ("Shared Items", "/sharing", "btn2"),
        ])
    if role == "worker":
        return grid("Worker Dashboard", "Field-friendly access. Money, admin tools, bookkeeping, and internal files stay hidden.", [
            ("Shared Items", "/sharing", ""), ("Mobile View", "/mobile", "btn2"),
            ("Live Chat", "/chat", "btn2"), ("Account", "/account/change-password", "btn2"),
        ])
    if role == "helper":
        return grid("Helper Dashboard", "Field helper access — shared job items, mobile view, and team chat.", [
            ("Shared Items", "/sharing", ""), ("Mobile View", "/mobile", "btn2"),
            ("Live Chat", "/chat", "btn2"), ("Jobs (read)", "/jobs", "btn2"),
        ])
    if role == "subcontractor":
        return grid("Subcontractor Dashboard", "Limited outside-worker access. W-9 and insurance onboarding required before pay.", [
            ("Shared Items", "/sharing", ""), ("Mobile View", "/mobile", "btn2"),
            ("Apply / Update Info", "/apply", "btn2"),
        ])
    if role == "guest":
        return grid("Guest / Applicant", "Apply to work with J&R. No company access until owner approves your application and account.", [
            ("Apply for Work", "/apply", ""), ("Request Login Account", "/register", "btn2"),
            ("Mobile Info", "/mobile", "btn2"),
        ])
    if role == "viewer":
        return grid("Read-only Dashboard", "Review permitted company information only. Editing and money/admin tools stay hidden.", [
            ("Shared Items", "/sharing", ""), ("Mobile View", "/mobile", "btn2"),
            ("Account", "/account/change-password", "btn2"),
        ])
    if role == "customer":
        return grid("Customer Quick Actions", "Customer portal only: submit work requests, shared customer items, and office announcements.", [
            ("Create Job Request", "/customer/request", ""), ("View My Requests", "/customer/requests", "btn2"),
            ("Shared With Me", "/sharing", "btn2"), ("Office Announcements", "/chat", "btn2"),
            ("Mobile Portal", "/mobile", "btn2"), ("Account", "/account/change-password", "btn2"),
        ])
    return grid("External Access Center", "Minimal outside access. You only see items specifically shared by J&R.", [
        ("Open Shared Items", "/sharing", ""), ("Mobile View", "/mobile", "btn2"),
        ("Account", "/account/change-password", "btn2"),
    ])
@app.route("/account/change-password", methods=["GET", "POST"])
@login_required()
def change_password():
    user = current_user()
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not verify_password(current, user["salt"], user["password_hash"]):
            flash("Current password is required before changing your password.", "error")
        elif new_password != confirm:
            flash("New password and confirmation do not match.", "error")
        else:
            is_admin_change = (user["username"] == DEFAULT_ADMIN_USERNAME or normalize_role_for_session(user["role"]) == "admin")
            mastery = request.form.get("mastery_key", "").strip()
            ok, msg = enforce_new_password_policy(new_password, mastery)
            if not ok:
                flash(msg, "error")
            else:
                salt, ph = hash_password(new_password)
                db().execute("UPDATE users SET salt=?, password_hash=?, must_change_password=0 WHERE id=?", (salt, ph, user["id"]))
                if user["username"] == DEFAULT_ADMIN_USERNAME:
                    mark_admin_password_changed(db())
                    db().execute("UPDATE online_sessions SET active=0, revoked=1, revoke_reason=? WHERE username=? AND session_id<>?", ("Admin password changed; other sessions revoked", DEFAULT_ADMIN_USERNAME, session.get("sid", "")))
                    log_security_event("admin_password_changed", user["username"], "Owner/admin password changed; default admin disabled and other admin sessions revoked", "WARN")
                else:
                    log_security_event("password_changed", user["username"], "User changed own password", "INFO")
                db().commit()
                flash("Password changed. The default admin login is now disabled for this business database." if user["username"] == DEFAULT_ADMIN_USERNAME else "Password changed.", "success")
                return redirect(url_for("setup_complete"))
    from app.densus_policy import password_policy_summary
    policy_note = password_policy_summary()
    body = f"""
    <div class='card card-narrow'><h2>Change Password</h2>
      <p class='muted'>{html.escape(policy_note)} Passwords are stored as hashes, not readable text.</p>
      <form method='post'>
        <p><label>Current password</label><input type='password' name='current_password' autocomplete='current-password'></p>
        <p><label>New password</label><input type='password' name='new_password' autocomplete='new-password'></p>
        <p><label>Confirm new password</label><input type='password' name='confirm_password' autocomplete='new-password'></p>
        <p><label>Mastery key (only if restoring first-setup password)</label><input type='password' name='mastery_key' autocomplete='off' placeholder='Emergency key — optional'></p>
        <button>Save New Password</button> <a class='btn btn2' href='/logout'>Cancel / Logout</a>
      </form>
    </div>
    """
    return layout("Change Password", body, "admin" if user and normalize_role_for_session(user["role"]) == "admin" else "dashboard")

@app.route("/owner-security-status")
@login_required("view_admin")
def owner_security_status():
    default_active = is_default_admin_password_active()
    owner_done = get_app_setting("owner_setup_complete", "0") == "1"
    body = f"""
    <div class='card'><h2>Owner Login Security</h2>
      <div class='grid'>
        <div class='stat'>First-setup login<b>{'ACTIVE' if default_active else 'Disabled'}</b><span class='muted'>{'Change ivygrows password before sharing access.' if default_active else 'Your changed owner password is preserved across updates.'}</span></div>
        <div class='stat'>Owner Setup<b>{'Complete' if owner_done else 'Required'}</b><span class='muted'>Tracked in this business database.</span></div>
        <div class='stat'>Remote First-Setup Login<b>Blocked</b><span class='muted'>ivygrows/ivygrows cannot be used from phones, LAN, or cloud.</span></div>
      </div>
      <p><a class='btn' href='/account/change-password'>Change Owner/Admin Password</a></p>
    </div>
    """
    return layout("Owner Security Status", body, "admin")

@app.route("/setup-complete")
@login_required("view_dashboard")
def setup_complete():
    user = current_user()
    role = user["role"] if user else "viewer"
    body = f"""
    <div class='card'><h2>Setup / Login Verified</h2>
      <p>Your login was verified and the program is ready to open the correct dashboard for your account.</p>
      <div class='grid'>
        <div class='stat'>Account<b>{html.escape(session.get('username',''))}</b><span class='muted'>{html.escape(role_display(role))}</span></div>
        <div class='stat'>Device Policy<b>90 Days</b><span class='muted'>Remembered only if the checkbox was selected during login.</span></div>
        <div class='stat'>Security<b>Active</b><span class='muted'>Passwords hashed, role permissions filtered, admin tools protected.</span></div>
      </div>
      <p><a class='btn' href='{url_for('dashboard')}'>Open My Dashboard</a> <a class='btn btn2' href='/account/change-password'>Change Password</a> <a class='btn btn2' href='/setup-status'>Run Setup / Verification Center</a></p>
    </div>
    <div class='card'><h2>Recommended next steps</h2><ol><li>Change first-setup ivygrows password if still active; updates preserve your new password.</li><li>Run Dropbox Live Check and backup sync from Admin → Dropbox Business.</li><li>Run Self Setup + Verify from the Start Center.</li><li>Use customer/external accounts only for customer-safe information.</li></ol></div>
    """
    return layout("Setup Complete", body, "dashboard")
@app.route("/")
@login_required("view_dashboard")
def dashboard():
    conn = db()
    user = current_user()
    role = normalize_role_for_session(user["role"] if user else "viewer")
    perms = get_user_permissions(user["id"], role) if user else set()
    if role == "non_company":
        shared_files = conn.execute("SELECT COUNT(*) FROM shared_files WHERE active=1 AND shared_with_role='non_company'").fetchone()[0]
        shared_jobs = conn.execute("SELECT COUNT(*) FROM shared_jobs WHERE active=1 AND shared_with_role='non_company'").fetchone()[0]
        body = f"""
        <div class='grid'>
          <div class='stat'>Account Type<b>{html.escape(role_display(role))}</b><span class='muted'>Minimal outside access</span></div>
          <div class='stat'>Shared Files<b>{shared_files}</b><span class='muted'>Only items intentionally shared to external users</span></div>
          <div class='stat'>Shared Jobs<b>{shared_jobs}</b><span class='muted'>No full job list or money access</span></div>
        </div>
        {role_command_center(role, perms)}
        <div class='card'><h2>What this account cannot access</h2><ul><li>No payroll, bookkeeping, expenses, tax records, or full file explorer.</li><li>No full customer/job database unless a specific item is shared.</li><li>No admin, device, hosting, or program setup tools.</li></ul></div>
        """
        return layout("External Dashboard", body, "dashboard")
    if role == "customer":
        profile = conn.execute("SELECT * FROM customer_user_profiles WHERE user_id=?", (user["id"],)).fetchone()
        if not profile:
            conn.execute("""INSERT INTO customer_user_profiles (user_id, username, display_name, email, phone, address, created_at, updated_at, notes)
                          VALUES (?,?,?,?,?,?,?,?,?)""", (user["id"], user["username"], user["display_name"] or user["username"], user["email"] if "email" in user.keys() else None, user["phone"] if "phone" in user.keys() else None, "", now_iso(), now_iso(), "Auto-created customer portal profile."))
            conn.commit()
            profile = conn.execute("SELECT * FROM customer_user_profiles WHERE user_id=?", (user["id"],)).fetchone()
        reqs = conn.execute("SELECT COUNT(*) FROM customer_job_requests WHERE customer_user_id=?", (profile["id"],)).fetchone()[0]
        open_reqs = conn.execute("SELECT COUNT(*) FROM customer_job_requests WHERE customer_user_id=? AND status NOT IN ('Closed','Cancelled','Converted to Job')", (profile["id"],)).fetchone()[0]
        recent = conn.execute("SELECT * FROM customer_job_requests WHERE customer_user_id=? ORDER BY submitted_at DESC, id DESC LIMIT 8", (profile["id"],)).fetchall()
        rows = "".join(f"<tr><td>{r['id']}</td><td>{html.escape(r['request_title'] or '')}</td><td>{html.escape(r['service_type'] or '')}</td><td>{html.escape(r['status'] or '')}</td><td>{html.escape(r['submitted_at'] or '')}</td></tr>" for r in recent)
        body = f"""
        <div class='grid'>
          <div class='stat'>Account Type<b>Customer</b><span class='muted'>Customer-only portal</span></div>
          <div class='stat'>Open Requests<b>{open_reqs}</b><span class='muted'>Requests J&R needs to review/complete</span></div>
          <div class='stat'>Total Requests<b>{reqs}</b><span class='muted'>Your submitted requests</span></div>
        </div>
        {role_command_center(role, perms)}
        <div class='card'><h2>Customer Dashboard</h2><p>This dashboard is limited to your customer-facing information. You can submit job requests and view request status. Internal job costing, payroll, bookkeeping, and other customers are hidden.</p><p class='muted'>For best results, include the property address, access notes, timeline, and photos/attachment notes with each request.</p></div>
        <div class='card'><h2>Recent Requests</h2><table><tr><th>ID</th><th>Request</th><th>Type</th><th>Status</th><th>Submitted</th></tr>{rows or '<tr><td colspan=5>No customer requests yet.</td></tr>'}</table></div>
        <div class='card'><h2>Customer privacy</h2><ul><li>You only see your request records and customer-shared information.</li><li>You cannot see J&R internal notes, payroll, job-costing, tax records, file explorer, or admin settings.</li><li>J&R may convert an approved request into an internal job record after owner review.</li></ul></div>
        """
        return layout("Customer Dashboard", body, "customer")
    job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    active_jobs = conn.execute("SELECT COUNT(*) FROM jobs WHERE status NOT LIKE 'Closed%'").fetchone()[0]
    files_count = conn.execute("SELECT COUNT(*) FROM file_index").fetchone()[0]
    online = conn.execute("SELECT COUNT(*) FROM online_sessions WHERE active=1 AND revoked=0 AND last_seen >= ?", ((dt.datetime.now()-dt.timedelta(minutes=15)).isoformat(timespec="seconds"),)).fetchone()[0]
    if "view_money" in perms:
        gross = conn.execute("SELECT COALESCE(SUM(paid),0) FROM jobs").fetchone()[0]
        open_ar = conn.execute("SELECT COALESCE(SUM(price-paid),0) FROM jobs WHERE price>paid").fetchone()[0]
        exp = conn.execute("SELECT COALESCE(SUM(amount),0) FROM expenses").fetchone()[0]
        workers = conn.execute("SELECT COALESCE(SUM(amount),0) FROM worker_payments WHERE status='Paid'").fetchone()[0]
        owner_draws = conn.execute("SELECT COALESCE(SUM(amount),0) FROM owner_draws").fetchone()[0] if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='owner_draws'").fetchone() else 0
        money_cards = f"""<div class="stat">Paid Income<b>{money(gross)}</b></div><div class="stat">Open Receivables<b>{money(open_ar)}</b></div><div class="stat">Expenses<b>{money(exp)}</b></div><div class="stat">Worker Pay<b>{money(workers)}</b></div><div class="stat">Owner Draws<b>{money(owner_draws or 0)}</b></div>"""
        money_cols = "<th>Price</th><th>Paid</th>"
        row_fmt = lambda r: f"<tr><td>{r['id']}</td><td>{html.escape(r['job_name'])}</td><td>{html.escape(r['status'] or '')}</td><td>{money(r['price'])}</td><td>{money(r['paid'])}</td></tr>"
    else:
        money_cards = ""
        money_cols = ""
        row_fmt = lambda r: f"<tr><td>{r['id']}</td><td>{html.escape(r['job_name'])}</td><td>{html.escape(r['status'] or '')}</td></tr>"
    rows = conn.execute("SELECT j.*, c.name AS customer FROM jobs j LEFT JOIN customers c ON c.id=j.customer_id ORDER BY j.updated_at DESC, j.id DESC LIMIT 12").fetchall()
    job_rows = "".join(row_fmt(r) for r in rows)
    tools = ""
    if "view_files" in perms:
        tools += " <a class='btn btn2' href='/files'>Files</a>"
    if "audit" in perms:
        tools += " <a class='btn btn2' href='/health/run'>Run Health Check</a>"
    body = f"""
    <div class="grid">
      {money_cards}
      <div class="stat">Active Jobs<b>{active_jobs}</b></div><div class="stat">Total Jobs<b>{job_count}</b></div>
      <div class="stat">Indexed Files<b>{files_count if 'view_files' in perms else 'Limited'}</b></div><div class="stat">Online Users<b>{online}</b></div>
    </div>
    {role_command_center(role, perms)}
    """
    from app.dashboard_config import render_dashboard_sections
    body += render_dashboard_sections(role, perms, densus_access=session_densus_access())
    if "view_jobs" in perms:
        body += f"""<div class="card"><h2>Current Jobs</h2><table><tr><th>ID</th><th>Job</th><th>Status</th>{money_cols}</tr>{job_rows}</table></div>"""
    body += f"""<div class="card"><h2>Your Access</h2><p><b>Role:</b> {html.escape(role_display(role))}</p><p class="muted">Sign-in required for every user. PC verified at login. Use tiles above for all features.</p></div>"""
    return layout("Dashboard", body, "dashboard")
@app.route("/jobs", methods=["GET", "POST"])
@login_required("view_jobs")
def jobs():
    conn = db()
    if request.method == "POST":
        user = current_user(); perms = get_user_permissions(user["id"], user["role"])
        if "edit_jobs" not in perms:
            abort(403)
        name = request.form.get("job_name", "").strip()
        if not name:
            flash("Job name is required.", "error")
        else:
            conn.execute("INSERT INTO jobs (job_name,address,scope,status,price,deposit,paid,payment_method,tax_status,notes,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (name, request.form.get("address"), request.form.get("scope"), request.form.get("status") or "Lead", parse_float(request.form.get("price")), parse_float(request.form.get("deposit")), parse_float(request.form.get("paid")), request.form.get("payment_method"), request.form.get("tax_status"), request.form.get("notes"), now_iso(), now_iso()))
            conn.commit(); log_event("Jobs", f"Added job: {name}"); flash("Job saved.", "success")
        return redirect(url_for("jobs"))
    rows = conn.execute("SELECT * FROM jobs ORDER BY updated_at DESC, id DESC").fetchall()
    trs = "".join(f"<tr><td>{r['id']}</td><td>{html.escape(r['job_code'] or '')}</td><td>{html.escape(r['job_name'])}</td><td>{html.escape(r['status'] or '')}</td><td>{money(r['price'])}</td><td>{money(r['deposit'])}</td><td>{money(r['paid'])}</td><td>{html.escape(r['notes'] or '')}</td></tr>" for r in rows)
    form = """
    <div class="card"><h2>Add Job</h2><form method="post"><div class="row3"><p><label>Job Name</label><input name="job_name"></p><p><label>Status</label><select name="status"><option>Lead</option><option>Estimate Sent</option><option>Approved</option><option>Active</option><option>Waiting Payment</option><option>Closed Paid</option><option>Closed Unpaid</option></select></p><p><label>Price</label><input name="price"></p></div><div class="row3"><p><label>Deposit</label><input name="deposit"></p><p><label>Paid</label><input name="paid"></p><p><label>Payment Method</label><input name="payment_method"></p></div><p><label>Address</label><input name="address"></p><p><label>Scope</label><textarea name="scope"></textarea></p><p><label>Notes</label><textarea name="notes"></textarea></p><button>Save Job</button></form></div>
    """
    body = form + f"<div class='card'><h2>Jobs</h2><table><tr><th>ID</th><th>Code</th><th>Job</th><th>Status</th><th>Price</th><th>Deposit</th><th>Paid</th><th>Notes</th></tr>{trs}</table></div>"
    return layout("Jobs", body, "jobs")
@app.route("/expenses", methods=["GET", "POST"])
@login_required("view_money")
def expenses():
    conn = db()
    if request.method == "POST":
        user = current_user(); perms = get_user_permissions(user["id"], user["role"])
        if "edit_money" not in perms:
            abort(403)
        conn.execute("INSERT INTO expenses (job_id,category,vendor,description,amount,paid_by,receipt_status,expense_date,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (request.form.get("job_id") or None, request.form.get("category"), request.form.get("vendor"), request.form.get("description"), parse_float(request.form.get("amount")), request.form.get("paid_by"), request.form.get("receipt_status"), request.form.get("expense_date") or dt.date.today().isoformat(), now_iso()))
        conn.commit(); log_event("Expenses", "Added expense record"); flash("Expense saved.", "success"); return redirect(url_for("expenses"))
    jobs = conn.execute("SELECT id, job_name FROM jobs ORDER BY job_name").fetchall()
    job_opts = '<option value="">No job / overhead</option>' + ''.join(f'<option value="{j["id"]}">{html.escape(j["job_name"])}</option>' for j in jobs)
    rows = conn.execute("SELECT e.*, j.job_name FROM expenses e LEFT JOIN jobs j ON j.id=e.job_id ORDER BY e.expense_date DESC, e.id DESC").fetchall()
    trs = ''.join(f"<tr><td>{html.escape(r['expense_date'] or '')}</td><td>{html.escape(r['job_name'] or 'Overhead')}</td><td>{html.escape(r['category'] or '')}</td><td>{html.escape(r['vendor'] or '')}</td><td>{money(r['amount'])}</td><td>{html.escape(r['receipt_status'] or '')}</td></tr>" for r in rows)
    body = f"""
    <div class="card"><h2>Add Expense</h2><form method="post"><div class="row3"><p><label>Job</label><select name="job_id">{job_opts}</select></p><p><label>Category</label><input name="category"></p><p><label>Amount</label><input name="amount"></p></div><div class="row3"><p><label>Vendor</label><input name="vendor"></p><p><label>Paid By</label><input name="paid_by"></p><p><label>Receipt Status</label><input name="receipt_status" value="Needs receipt"></p></div><p><label>Description</label><textarea name="description"></textarea></p><button>Save Expense</button></form></div>
    <div class="card"><h2>Expenses</h2><table><tr><th>Date</th><th>Job</th><th>Category</th><th>Vendor</th><th>Amount</th><th>Receipt</th></tr>{trs}</table></div>"""
    return layout("Expenses", body, "expenses")
def analyze_file(path: Path) -> Tuple[str, str]:
    name = path.name.lower()
    ext = path.suffix.lower()
    keywords = []
    analysis = []
    mapping = {
        "invoice": "invoice", "estimate": "estimate", "receipt": "receipt", "lowe": "materials", "payroll": "worker pay", "tax": "tax",
        "w9": "W-9", "insurance": "insurance", "brake": "vehicle/brake job", "cumberland": "Ray Joyner", "billy": "Billy",
        "401": "401 East 2nd", "403": "403 East 2nd", "mintz": "Mintz Cemetery", "deck": "deck", "billing": "billing"
    }
    for key, value in mapping.items():
        if key in name:
            keywords.append(value)
    if ext in [".pdf"]:
        analysis.append("PDF document")
    elif ext in [".png", ".jpg", ".jpeg"]:
        analysis.append("Image/evidence file")
    elif ext in [".csv", ".xlsx"]:
        analysis.append("Spreadsheet/business data")
    elif ext in [".txt", ".md"]:
        analysis.append("Text note/log")
    if keywords:
        analysis.append("Matched: " + ", ".join(sorted(set(keywords))))
    return ", ".join(sorted(set(keywords))), "; ".join(analysis) or "Indexed file"
def scan_sources() -> Dict[str, int]:
    conn = direct_db()
    counts = {"sources": 0, "files": 0, "errors": 0}
    try:
        sources = conn.execute("SELECT * FROM file_sources WHERE active=1").fetchall()
        for source in sources:
            counts["sources"] += 1
            folder = Path(source["folder_path"]).expanduser()
            if not folder.exists():
                health_event("WARN", "File Source", f"Missing source folder: {folder}")
                counts["errors"] += 1
                continue
            total_size = 0; file_count = 0
            for p in folder.rglob("*"):
                if not p.is_file():
                    continue
                try:
                    stat = p.stat(); keywords, analysis = analyze_file(p)
                    conn.execute("""INSERT INTO file_index (source_id,file_path,file_name,extension,size,modified_at,discovered_at,keywords,analysis)
                                    VALUES (?,?,?,?,?,?,?,?,?)
                                    ON CONFLICT(file_path) DO UPDATE SET file_name=excluded.file_name,extension=excluded.extension,size=excluded.size,modified_at=excluded.modified_at,discovered_at=excluded.discovered_at,keywords=excluded.keywords,analysis=excluded.analysis""",
                                 (source["id"], str(p), p.name, p.suffix.lower(), stat.st_size, dt.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"), now_iso(), keywords, analysis))
                    file_count += 1; total_size += stat.st_size; counts["files"] += 1
                except Exception as exc:
                    counts["errors"] += 1
                    health_event("ERROR", "File Scan", f"Failed indexing {p}: {exc}")
            conn.execute("INSERT INTO source_summaries (source_id,summary_time,file_count,total_size,notes) VALUES (?,?,?,?,?)", (source["id"], now_iso(), file_count, total_size, "Refresh complete"))
        conn.commit()
    finally:
        conn.close()
    return counts
@app.route("/files")
@login_required("view_files")
def files():
    q = request.args.get("q", "").strip()
    rows = []
    if q:
        like = f"%{q}%"
        rows = db().execute("SELECT fi.*, fs.label FROM file_index fi LEFT JOIN file_sources fs ON fs.id=fi.source_id WHERE fi.file_name LIKE ? OR fi.keywords LIKE ? OR fi.analysis LIKE ? ORDER BY fi.modified_at DESC LIMIT 300", (like, like, like)).fetchall()
    else:
        rows = db().execute("SELECT fi.*, fs.label FROM file_index fi LEFT JOIN file_sources fs ON fs.id=fi.source_id ORDER BY fi.modified_at DESC LIMIT 300").fetchall()
    trs = ''.join(f"<tr><td>{html.escape(r['file_name'])}</td><td>{html.escape(r['label'] or '')}</td><td>{html.escape(r['extension'] or '')}</td><td>{r['size'] or 0}</td><td>{html.escape(r['keywords'] or '')}</td><td>{html.escape(r['analysis'] or '')}</td><td><a href='/files/open/{r['id']}'>Open</a></td></tr>" for r in rows)
    sources = db().execute("SELECT * FROM file_sources ORDER BY label").fetchall()
    src_rows = ''.join(f"<tr><td>{s['id']}</td><td>{html.escape(s['label'])}</td><td>{html.escape(s['source_type'] or '')}</td><td>{html.escape(s['folder_path'])}</td><td>{'Active' if s['active'] else 'Off'}</td></tr>" for s in sources)
    body = f"""
    <div class="card"><h2>Source Refresh</h2><a class="btn" href="/files/refresh">Refresh and Analyze Files</a><p class="muted">Sources can include local Dropbox folders, program evidence, exports, and ChatGPT import files.</p></div>
    <div class="card"><h2>Upload Evidence / Business File</h2><form method="post" action="/files/upload" enctype="multipart/form-data"><div class="row"><input type="file" name="file"><button>Upload to Evidence Folder</button></div></form><p class="muted">Managers and admins can upload files. Viewers and workers are read-only.</p></div>
    <div class="card"><h2>File Search</h2><form method="get"><div class="row"><input name="q" value="{html.escape(q)}" placeholder="Search invoices, receipts, Billy, Lowe, tax..."><button>Search</button></div></form></div>
    <div class="card"><h2>Indexed Files</h2><table><tr><th>Name</th><th>Source</th><th>Type</th><th>Size</th><th>Keywords</th><th>Analysis</th><th>Action</th></tr>{trs}</table></div>
    <div class="card"><h2>File Sources</h2><table><tr><th>ID</th><th>Label</th><th>Type</th><th>Folder</th><th>Status</th></tr>{src_rows}</table><p><a class="btn btn2" href="/files/sources">Manage Sources</a></p></div>"""
    return layout("File Explorer", body, "files")
@app.route("/files/refresh")
@login_required("view_files")
def refresh_files():
    counts = scan_sources()
    log_event("File Refresh", f"Scanned {counts['files']} files from {counts['sources']} sources with {counts['errors']} errors")
    flash(f"Refresh complete: {counts['files']} files scanned, {counts['errors']} issues.", "success" if not counts["errors"] else "warning")
    return redirect(url_for("files"))
@app.route("/files/open/<int:file_id>")
@login_required("view_files")
def open_file(file_id: int):
    from app.file_access_security import (
        get_allowed_file_roots,
        path_under_allowed_roots,
        role_may_open_indexed_file,
    )

    user = current_user()
    role = session.get("role") or (user["role"] if user else "viewer")
    row = db().execute("SELECT file_path, file_name FROM file_index WHERE id=?", (file_id,)).fetchone()
    if not row:
        abort(404)
    path = Path(row["file_path"])
    allowed, reason = role_may_open_indexed_file(role, str(path))
    if not allowed:
        log_security_event(
            "file_access_denied",
            session.get("username", ""),
            f"Blocked indexed file {row['file_name']}: {reason}",
            "WARN",
        )
        abort(403)
    if not path.exists() or not path.is_file():
        flash("File is no longer available at that path. Refresh sources.", "warning")
        return redirect(url_for("files"))
    roots = get_allowed_file_roots(BASE_DIR)
    if roots and not path_under_allowed_roots(path, roots):
        log_security_event(
            "file_path_outside_roots",
            session.get("username", ""),
            f"Blocked path outside allowed roots: {path}",
            "ERROR",
        )
        abort(403)
    return send_file(path, as_attachment=False)
@app.route("/files/sources", methods=["GET", "POST"])
@login_required("manage_files")
def manage_sources():
    if request.method == "POST":
        db().execute("INSERT INTO file_sources (label,source_type,folder_path,active,created_at) VALUES (?,?,?,?,?)", (request.form.get("label"), request.form.get("source_type"), request.form.get("folder_path"), 1, now_iso()))
        db().commit(); flash("Source added.", "success"); return redirect(url_for("manage_sources"))
    rows = db().execute("SELECT * FROM file_sources ORDER BY id").fetchall()
    trs = ''.join(f"<tr><td>{r['id']}</td><td>{html.escape(r['label'])}</td><td>{html.escape(r['source_type'] or '')}</td><td>{html.escape(r['folder_path'])}</td><td>{r['active']}</td></tr>" for r in rows)
    body = f"""<div class="card"><h2>Add Source</h2><form method="post"><div class="row3"><p><label>Label</label><input name="label"></p><p><label>Type</label><select name="source_type"><option>dropbox-local</option><option>local</option><option>chatgpt</option></select></p><p><label>Folder Path</label><input name="folder_path" placeholder="C:\\Users\\...\\Dropbox\\Invoices2026 1.0"></p></div><button>Add Source</button></form></div>
    <div class="card"><h2>Sources</h2><table><tr><th>ID</th><th>Label</th><th>Type</th><th>Path</th><th>Active</th></tr>{trs}</table></div>"""
    return layout("Manage File Sources", body, "files")
@app.route("/owner-recovery", methods=["GET", "POST"])
def owner_recovery():
    init_db()
    allowed = trusted_owner_local_request()
    if not allowed:
        try:
            db().execute("INSERT INTO owner_recovery_events (event_time,action,username,ip_address,user_agent,trusted_admin_device_id,result,notes) VALUES (?,?,?,?,?,?,?,?)",
                         (now_iso(), "view", "admin", client_ip(), request.headers.get("User-Agent", ""), get_device_id(), "Denied", "Owner recovery attempted outside trusted local host device"))
            db().commit()
        except Exception:
            pass
        return layout("Owner Recovery", "<div class='card'><h2>Owner Recovery Locked</h2><p>This recovery tool only works from Jacob's trusted local host computer at the local address.</p><p class='muted'>Use normal admin login or ask the owner to use the host PC.</p></div>", "admin")
    if request.method == "POST":
        new_password = request.form.get("new_password", "").strip()
        confirm = request.form.get("confirm", "").strip()
        mastery = request.form.get("mastery_key", "").strip()
        ok, msg = enforce_new_password_policy(new_password, mastery)
        if not ok:
            flash(msg, "error")
        elif new_password != confirm:
            flash("Passwords do not match.", "error")
        else:
            salt, ph = hash_password(new_password)
            db().execute("UPDATE users SET salt=?, password_hash=?, must_change_password=0, active=1 WHERE username=?", (salt, ph, DEFAULT_ADMIN_USERNAME))
            mark_admin_password_changed(db())
            db().execute("INSERT INTO owner_recovery_events (event_time,action,username,ip_address,user_agent,trusted_admin_device_id,result,notes) VALUES (?,?,?,?,?,?,?,?)",
                         (now_iso(), "reset_admin_password", "admin", client_ip(), request.headers.get("User-Agent", ""), get_device_id(), "OK", "Transparent owner recovery used on trusted local host device"))
            db().commit()
            log_security_event("owner_recovery_used", "admin", "Owner emergency recovery reset admin password from trusted local host device", "WARN")
            flash("Admin password reset from trusted owner device. This action was logged.", "success")
            return redirect(url_for("login"))
    body = """
    <div class='card card-narrow'><h2>Owner Emergency Recovery</h2>
    <p>This is a transparent owner-only recovery tool for Jacob's trusted host PC. It does not access other users' computers and every use is logged.</p>
    <form method='post'><p><label>New owner password</label><input type='password' name='new_password'></p><p><label>Confirm password</label><input type='password' name='confirm'></p><p><label>Mastery key (required to restore ivygrows default)</label><input type='password' name='mastery_key' autocomplete='off'></p><button>Reset Owner Password</button></form>
    <p class='muted'>Use only if the normal admin password is lost. Choose a strong password and keep it private.</p></div>
    """
    return layout("Owner Recovery", body, "admin")
@app.route("/forget-this-device")
@login_required()
def forget_this_device():
    token = get_client_device_token()
    if token:
        try:
            db().execute("UPDATE known_devices SET trust_status='forgotten', notes=? WHERE device_fingerprint=?", (f"Forgotten by {session.get('username')} at {now_iso()}", _hash_device_token(token)))
            db().commit()
            log_security_event("device_forgotten", session.get("username", ""), "User cleared remembered device cookie", "INFO")
        except Exception:
            pass
    resp = redirect(url_for("dashboard"))
    clear_device_cookie(resp)
    flash("This browser/device has been forgotten. You can log in again to re-register it.", "success")
    return resp
@app.route("/admin/devices")
@login_required("manage_devices")
def admin_devices():
    rows = db().execute("SELECT * FROM known_devices ORDER BY last_seen DESC LIMIT 300").fetchall()
    trs = ''.join(f"<tr><td>{r['id']}</td><td><b>{html.escape(r['username'] or '')}</b><br><span class='muted'>User ID: {r['user_id'] or ''}</span></td><td>{html.escape(r['device_label'] or '')}<br><span class='muted'>{html.escape((r['last_user_agent'] or '')[:90])}</span></td><td>{html.escape(r['last_ip'] or '')}<br><span class='muted'>First: {html.escape(r['first_ip'] or '')}</span></td><td><span class='badge'>{html.escape(r['trust_status'] or 'observed')}</span></td><td>{html.escape(r['first_seen'] or '')}<br>{html.escape(r['last_seen'] or '')}</td><td><a class='btn' href='/admin/device/{r['id']}/trust'>Trust</a> <a class='btn warn' href='/admin/device/{r['id']}/observe'>Observe</a> <a class='btn danger' href='/admin/device/{r['id']}/block'>Block</a></td></tr>" for r in rows)
    body = f"""
    <div class='card'><h2>Known Devices</h2><p>Devices are remembered only when the user checks the remember-this-device box during login. The remembered device lasts 90 days, uses a first-party HttpOnly/SameSite cookie plus username, IP address, and browser/device details, and the cookie stores only an opaque random token. The database stores only its hash/fingerprint for auditing, expiration, and device blocking.</p>
    <table><tr><th>ID</th><th>User</th><th>Device</th><th>IP Address</th><th>Status</th><th>Seen</th><th>Action</th></tr>{trs}</table></div>
    <div class='card'><h2>Policy</h2><ul><li>Trust marks a consented device as recognized for auditing.</li><li>Remembered devices expire after 90 days and require another successful login/checkbox verification.</li><li>Block prevents that remembered browser/device token from logging in again.</li><li>No hidden backdoor is used. Admin actions are visible, permission-based, and logged.</li><li>HTTPS/public host mode uses Secure cookies. Local LAN HTTP keeps cookies working with HttpOnly + SameSite protection.</li></ul></div>
    """
    return layout("Device Manager", body, "devices")
@app.route("/admin/device/<int:device_id>/<action>")
@login_required("manage_devices")
def admin_device_action(device_id: int, action: str):
    if action not in {"trust", "observe", "block"}:
        abort(404)
    status = {"trust": "trusted", "observe": "observed", "block": "blocked"}[action]
    now = now_iso()
    if status == "trusted":
        db().execute("UPDATE known_devices SET trust_status=?, approved_by=?, approved_at=?, notes=? WHERE id=?", (status, session.get("username"), now, "Trusted by admin", device_id))
    elif status == "blocked":
        db().execute("UPDATE known_devices SET trust_status=?, blocked_by=?, blocked_at=?, notes=? WHERE id=?", (status, session.get("username"), now, "Blocked by admin", device_id))
    else:
        db().execute("UPDATE known_devices SET trust_status=?, notes=? WHERE id=?", (status, "Returned to observed status by admin", device_id))
    db().commit()
    log_security_event("device_status_changed", session.get("username", ""), f"Device {device_id} set to {status}", "WARN" if status == "blocked" else "INFO")
    flash(f"Device set to {status}.", "success")
    return redirect(url_for("admin_devices"))
def _admin_user_role_cell(user_row: sqlite3.Row) -> str:
    """Inline account-type changer for Admin → Users table."""
    uid = int(user_row["id"])
    current = normalize_role_for_session(user_row["role"] or "viewer")
    display = role_display(current)
    if int(user_row["owner_account"] or 0) or user_row["username"] == DEFAULT_ADMIN_USERNAME:
        return f"<b>{html.escape(display)}</b><br><span class='muted'>Owner — fixed</span>"
    opts = role_select_options(current, exclude=("admin",))
    return (
        f"<b>{html.escape(display)}</b>"
        f"<form method='post' action='/admin/user/{uid}/role' style='margin-top:6px;display:flex;gap:6px;flex-wrap:wrap;align-items:center'>"
        f"<select name='role' style='min-width:160px'>{opts}</select>"
        f"<button class='btn btn2' type='submit'>Change type</button>"
        f"</form>"
    )
def _admin_empty_row(colspan: int, message: str) -> str:
    return f"<tr><td colspan='{colspan}' class='muted' style='text-align:center;padding:16px'>{html.escape(message)}</td></tr>"


def _require_admin_role():
    if normalize_role_for_session(session.get("role", "")) != "admin":
        abort(403)


def _admin_command_center_html() -> str:
    port = int(os.environ.get("JRC_PORT", "8765"))
    lan = get_lan_ip()
    pending_n = 0
    apps_n = 0
    densus_pending_n = 0
    try:
        pending_n = db().execute("SELECT COUNT(*) FROM account_requests WHERE status='Pending'").fetchone()[0]
    except Exception:
        pass
    try:
        from app.densus_access import pending_count

        densus_pending_n = pending_count(db())
    except Exception:
        pass
    try:
        apps_n = db().execute("SELECT COUNT(*) FROM job_applications WHERE status IN ('Pending','Review','Need Info')").fetchone()[0]
    except Exception:
        pass
    try:
        from app.admin_tools import get_admin_dashboard_status
        st = get_admin_dashboard_status()
        mod_ok = st.get("module_ok", True)
        mod_msg = html.escape(str(st.get("module_message", ""))[:180])
        mod_badge = "ok" if mod_ok else "red"
        host_badge = "ok" if st.get("host_status") == "OK" else "yellow"
        host_detail = html.escape(str(st.get("host_detail", ""))[:120])
        densus_badge = "ok" if st.get("densus_installed") else "yellow"
        densus_txt = "Installed on Desktop" if st.get("densus_installed") else "Not on Desktop — optional"
        db_badge = "ok" if st.get("database_exists") else "yellow"
        last_rep = html.escape(st.get("last_report") or "None yet")
    except Exception:
        mod_badge, mod_msg = "yellow", "Status unavailable"
        host_badge, host_detail = "yellow", ""
        densus_badge, densus_txt = "yellow", "Unknown"
        db_badge = "yellow"
        last_rep = "—"
    pending_badge = "red" if pending_n else "ok"
    apps_badge = "yellow" if apps_n else "ok"
    densus_badge_stat = "red" if densus_pending_n else ("ok" if densus_badge == "ok" else densus_badge)
    densus_stat_label = (
        f"{densus_pending_n} pending approval" if densus_pending_n else densus_txt
    )
    return f"""
    <div class="card"><h2>Owner Admin Command Center</h2>
      <p class="muted">v{html.escape(APP_VERSION)} · All owner tools in one place. Sign-in required for every user including admin.</p>
      <div class="grid">
        <div class="stat">Shared Host<span class="badge {host_badge}">{'Online' if host_badge=='ok' else 'Check'}</span><span class="muted">Port {port} · LAN <code>http://{html.escape(lan)}:{port}</code><br>{host_detail}</span></div>
        <div class="stat">Pending Logins<span class="badge {pending_badge}">{pending_n}</span><span class="muted">Account requests awaiting your approval</span></div>
        <div class="stat">Densus Access<span class="badge {densus_badge_stat}">{'Review' if densus_pending_n else ('OK' if densus_badge=='ok' else 'Setup')}</span><span class="muted">{html.escape(densus_stat_label)} — owner approves each admin</span></div>
        <div class="stat">Hire Applications<span class="badge {apps_badge}">{apps_n}</span><span class="muted">/apply submissions to review</span></div>
        <div class="stat">Python Modules<span class="badge {mod_badge}">{'OK' if mod_badge=='ok' else 'Fix'}</span><span class="muted">{mod_msg}</span></div>
        <div class="stat">Database<span class="badge {db_badge}">{'Found' if db_badge=='ok' else 'Missing'}</span><span class="muted">Business data on this PC</span></div>
      </div>
      <p class="muted">Last troubleshooter report: <code>{last_rep}</code></p>
    </div>
    <div class="card"><h2>Quick Actions</h2>
      <div class="action-grid">
        <a class="btn" href="/admin#pending-requests"><b>Review Login Requests</b><br><span class="muted" style="font-size:12px">{pending_n} pending — approve/deny + email notify</span></a>
        <a class="btn btn2" href="/applications"><b>Worker Applications</b><br><span class="muted" style="font-size:12px">Full hire forms (/apply)</span></a>
        <a class="btn btn2" href="/chat"><b>Live Chat</b><br><span class="muted" style="font-size:12px">Team chat + Office Announcements</span></a>
        <a class="btn btn2" href="/admin/new_user"><b>Add User</b><br><span class="muted" style="font-size:12px">Create account manually</span></a>
        <a class="btn btn2" href="/admin/devices"><b>Devices</b><br><span class="muted" style="font-size:12px">Trusted PCs and phones</span></a>
        <a class="btn btn2" href="/admin/dropbox"><b>Dropbox Sync</b><br><span class="muted" style="font-size:12px">Office records alignment</span></a>
        <a class="btn btn2" href="/admin/densus"><b>Densus Monitor</b><br><span class="muted" style="font-size:12px">Owner-approved — sessions + download</span></a>
        <a class="btn btn2" href="/admin/database/accounts"><b>Account DB</b><br><span class="muted" style="font-size:12px">Roles + permission overrides</span></a>
        <a class="btn btn2" href="/hosting"><b>Hosting / Mobile</b><br><span class="muted" style="font-size:12px">LAN + cloud setup</span></a>
        <a class="btn btn2" href="/connect"><b>Connection Test</b><br><span class="muted" style="font-size:12px">Phone / remote check</span></a>
        <a class="btn btn2" href="/business"><b>Business Hub</b><br><span class="muted" style="font-size:12px">Command center</span></a>
        <a class="btn btn2" href="/health"><b>System Check</b><br><span class="muted" style="font-size:12px">Verify before live use</span></a>
      </div>
      <p style="margin-top:14px">
        <a class="btn" href="/admin/troubleshooter">Open Full Troubleshooter</a>
        <a class="btn btn2" href="/security-audit">Security Audit</a>
        <a class="btn btn2" href="/backup">Backup ZIP</a>
        <a class="btn btn2" href="/cloud">Cloud Setup</a>
        <a class="btn btn2" href="/data">Data</a>
        <a class="btn btn2" href="/owner-security-status">Owner Security</a>
      </p>
      <form method="post" action="/admin/run-auto-repair" class="admin-repair-form" style="margin-top:12px;display:inline">
        <button type="submit">Run Full Auto-Repair (recommended)</button>
      </form>
      <form method="post" action="/admin/fix-launchers" class="admin-repair-form" style="margin-top:12px;display:inline;margin-left:8px">
        <button type="submit" class="btn btn2">Fix Module / Launcher Errors</button>
      </form>
      <p class="muted">File security: payroll/tax/internal files are admin/manager only. Customers use Shared Items only.</p>
    </div>
    <div class="card"><h2>Share Links (same Wi-Fi / VPN)</h2>
      <p><b>Mobile:</b> <code>http://{html.escape(lan)}:{port}/mobile</code></p>
      <p><b>Connection test:</b> <code>http://{html.escape(lan)}:{port}/connect</code></p>
      <p><b>Account request:</b> <code>http://{html.escape(lan)}:{port}/register</code></p>
      <p><b>Apply for work:</b> <code>http://{html.escape(lan)}:{port}/apply</code></p>
      <p><a class="btn" href="/connect" target="_blank">Open Connection Test Page</a></p>
    </div>"""
@app.route("/admin")
@login_required("view_admin")
def admin():
    online_cut = (dt.datetime.now() - dt.timedelta(minutes=15)).isoformat(timespec="seconds")
    online = db().execute("SELECT * FROM online_sessions WHERE active=1 AND revoked=0 AND last_seen >= ? ORDER BY last_seen DESC", (online_cut,)).fetchall()
    users = db().execute("SELECT id, username, display_name, role, active, must_change_password, created_at, last_login, last_ip_address, email, phone FROM users ORDER BY username").fetchall()
    pending = db().execute("SELECT * FROM account_requests WHERE status='Pending' ORDER BY created_at DESC").fetchall()
    reg_url = url_for('public_account_request', _external=True)
    security = db().execute("SELECT * FROM security_events ORDER BY id DESC LIMIT 12").fetchall() if db().execute("SELECT name FROM sqlite_master WHERE type='table' AND name='security_events'").fetchone() else []
    online_rows = ''.join(f"<tr><td><b>{html.escape(r['username'])}</b></td><td>{html.escape(r['role'] or '')}</td><td>{html.escape(r['ip_address'] or '')}</td><td><b>{html.escape(r['client_device_label'] or 'Unknown')}</b><br><span class='muted'>{html.escape((r['user_agent'] or '')[:80])}</span><br><span class='badge'>{html.escape(r['device_trust_status'] or 'observed')}</span></td><td>{html.escape(r['login_time'] or '')}</td><td>{html.escape(r['last_seen'] or '')}</td><td><a class='btn danger' href='/admin/revoke/{html.escape(r['session_id'])}'>End</a></td></tr>" for r in online)
    user_rows = ''.join(
        f"<tr><td>{r['id']}</td><td><b>{html.escape(r['username'])}</b><br><span class='muted'>{html.escape(r['email'] or '')}</span></td>"
        f"<td>{html.escape(r['display_name'] or '')}<br><span class='muted'>{html.escape(r['phone'] or '')}</span></td>"
        f"<td>{_admin_user_role_cell(r)}</td>"
        f"<td>{'Yes' if r['active'] else 'No'}</td>"
        f"<td>{html.escape(r['last_login'] or '')}<br><span class='muted'>Last IP: {html.escape(r['last_ip_address'] or '')}</span></td>"
        f"<td><a class='btn btn2' href='/admin/user/{r['id']}'>Full edit</a></td></tr>"
        for r in users
    )
    pending_rows = ''.join(
        f"<tr><td><b>{html.escape(r['requested_username'])}</b><br>{html.escape(r['display_name'] or '')}</td>"
        f"<td>{html.escape(role_display(r['requested_role'] or 'guest'))}</td>"
        f"<td>{html.escape(r['phone'] or '')}<br><span class='muted'>{html.escape(r['email'] or '')}</span></td>"
        f"<td>{html.escape(r['worker_type'] or '')}<br><span class='muted'>{html.escape(r['skills'] or '')}</span></td>"
        f"<td>{html.escape(r['request_ip'] or '')}<br><span class='muted'>{html.escape((r['request_user_agent'] or '')[:55])}</span></td>"
        f"<td>{html.escape(r['created_at'] or '')}</td>"
        f"<td><form method='post' action='/admin/request/{r['id']}/approve' style='display:inline'>"
        f"<select name='role'>{role_select_options(r['requested_role'] or 'guest', exclude=('admin', 'manager'))}</select>"
        f"<button>Approve</button></form> "
        f"<form method='post' action='/admin/request/{r['id']}/deny' style='display:inline'><button class='danger'>Deny</button></form></td></tr>"
        for r in pending
    )
    security_rows = ''.join(f"<tr><td>{html.escape(r['event_time'] or '')}</td><td>{html.escape(r['level'] or '')}</td><td>{html.escape(r['event_type'] or '')}</td><td>{html.escape(r['username'] or '')}</td><td>{html.escape(r['ip_address'] or '')}</td><td>{html.escape((r['message'] or '')[:120])}</td></tr>" for r in security)
    if not online:
        online_rows = _admin_empty_row(7, "No users online in the last 15 minutes.")
    if not users:
        user_rows = _admin_empty_row(7, "No users in database yet.")
    if not pending:
        pending_rows = _admin_empty_row(7, "No pending account requests.")
    if not security:
        security_rows = _admin_empty_row(6, "No security events logged yet.")
    body = f"""
    {_admin_command_center_html()}
    <div class="card"><h2>Shareable Account Request Link</h2><p>Send this link to workers or trusted users. <b>Owner/admin approval is required</b> before anyone can log in. Owner is emailed on each new request; requester is emailed on approve/deny.</p><p><input value="{html.escape(reg_url)}" readonly onclick="this.select()"></p><p><a class="btn" href="{html.escape(reg_url)}" target="_blank">Open Request Page</a></p><p class='muted'>Only owner/admin can approve or deny pending requests. Manager role cannot be granted via self-registration.</p></div>
    <div class="card" id="pending-requests"><h2>Pending Account Requests — Owner Approval Required</h2><table><tr><th>Requested User</th><th>Role</th><th>Contact</th><th>Worker Info</th><th>IP</th><th>Requested</th><th>Owner Action</th></tr>{pending_rows}</table></div>
    <div class="card"><h2>Current Online Sessions</h2><p><a class="btn btn2" href="/admin/devices">Open Device Manager</a></p><table><tr><th>User</th><th>Role</th><th>IP Address</th><th>Device / Browser</th><th>Login</th><th>Last Seen</th><th>Action</th></tr>{online_rows}</table></div>
    <div class="card"><h2>Users and Account Types</h2><p class='muted'>Change account type inline below, or use <b>Full edit</b> for password, contact info, and Owner/Admin promotion (mastery key).</p><p><a class="btn" href="/admin/new_user">Add User</a> <a class="btn btn2" href="/admin/export_users">Export User Index</a></p><table><tr><th>ID</th><th>Username</th><th>Name</th><th>Account Type</th><th>Active</th><th>Last Login</th><th>Action</th></tr>{user_rows}</table></div>
    <div class="card"><h2>Recent Security / Account Events</h2><table><tr><th>Time</th><th>Level</th><th>Type</th><th>User</th><th>IP</th><th>Message</th></tr>{security_rows}</table></div>
    <div class="card"><h2>Permissions by Role</h2><table><tr><th>Role</th><th>Permissions</th></tr>
    {''.join(f"<tr><td>{html.escape(ROLE_DISPLAY_NAMES.get(r, r))}</td><td>{permission_badges(r)}</td></tr>" for r in ROLE_LABELS if r != 'admin')}
    <tr><td>{html.escape(ROLE_DISPLAY_NAMES.get('admin', 'admin'))}</td><td>{permission_badges('admin')}</td></tr>
    </table></div><div class="card"><h2>Checks and Balances</h2><ul><li>Passwords are hashed, not stored as readable text.</li><li>Admins can revoke active sessions and identify users by username, IP address, browser/device information, and remembered device status.</li><li>Workers can request accounts from /register without installing the program; admins approve or deny access.</li><li>All major actions are timestamped in the business log.</li><li>Health checks inspect database, backups, sources, and default password risk.</li><li>Workers and viewers are read-only for money/file changes.</li><li>Use only trusted LAN/VPN or a properly secured cloud host for remote users.</li></ul></div>"""
    return layout("Admin Panel", body, "admin")
@app.route("/admin/request/<int:req_id>/approve", methods=["POST"])
@login_required("manage_users")
def approve_account_request(req_id: int):
    if not is_admin_role(session.get("role", "")):
        log_security_event("account_approval_denied", session.get("username", ""), "Non-admin attempted account approval", "WARN")
        abort(403)
    req = db().execute("SELECT * FROM account_requests WHERE id=?", (req_id,)).fetchone()
    if not req or req["status"] != "Pending":
        flash("Account request is not available or already reviewed.", "warning")
        return redirect(url_for("admin"))
    role = request.form.get("role") or req["requested_role"] or "worker"
    if role not in ROLE_LABELS:
        role = "worker"
    if role == "admin":
        flash("Admin role cannot be granted via account request approval.", "error")
        return redirect(url_for("admin"))
    if role == "manager":
        flash("Manager role cannot be granted via public account request. Create managers manually in Admin.", "error")
        return redirect(url_for("admin"))
    if db().execute("SELECT id FROM users WHERE username=?", (req["requested_username"],)).fetchone():
        db().execute("UPDATE account_requests SET status='Denied', reviewed_at=?, reviewed_by=?, admin_notes=? WHERE id=?", (now_iso(), session.get("username"), "Username already exists during approval", req_id))
        db().commit()
        flash("That username already exists. Request denied to prevent duplicate account.", "error")
        return redirect(url_for("admin"))
    cur = db().execute("""INSERT INTO users (username, display_name, role, salt, password_hash, active, must_change_password, created_at, notes, email, recovery_email, phone, title)
                      VALUES (?,?,?,?,?,1,0,?,?,?,?,?,?)""",
                      (req["requested_username"], req["display_name"], role, req["salt"], req["password_hash"], now_iso(), f"Approved from account request #{req_id}. IP: {req['request_ip']}", req["email"], req["recovery_email"], req["phone"], req["worker_type"]))
    user_id = cur.lastrowid
    from app.account_provisioning import provision_user_role_profiles
    provision_user_role_profiles(db(), user_id, req["requested_username"], role, req)
    db().execute("UPDATE account_requests SET status='Approved', reviewed_at=?, reviewed_by=?, admin_notes=? WHERE id=?", (now_iso(), session.get("username"), f"Approved as {role}", req_id))
    db().commit()
    log_event("Admin", f"Approved account request {req['requested_username']} as {role}")
    log_security_event("account_request_approved", req["requested_username"], f"Approved as {role} by owner/admin", "OK")
    try:
        from app.application_notifications import notify_requester_account_decision

        conn = db()
        n_ok, n_msg = notify_requester_account_decision(
            conn, req_id, "Approved", role, request_base_url=request.url_root.rstrip("/")
        )
        if n_ok:
            flash(f"Approved {req['requested_username']} as {role}. Requester emailed — they can sign in now.", "success")
        else:
            flash(f"Approved {req['requested_username']} as {role}. Email note: {n_msg}", "warning")
    except Exception as exc:
        flash(f"Approved {req['requested_username']} as {role}. Email notify error: {exc}", "warning")
    return redirect(url_for("admin"))
@app.route("/admin/request/<int:req_id>/deny", methods=["POST"])
@login_required("manage_users")
def deny_account_request(req_id: int):
    if not is_admin_role(session.get("role", "")):
        log_security_event("account_approval_denied", session.get("username", ""), "Non-admin attempted account denial", "WARN")
        abort(403)
    req = db().execute("SELECT * FROM account_requests WHERE id=?", (req_id,)).fetchone()
    if req and req["status"] == "Pending":
        db().execute("UPDATE account_requests SET status='Denied', reviewed_at=?, reviewed_by=?, admin_notes=? WHERE id=?", (now_iso(), session.get("username"), "Denied by owner/admin", req_id))
        db().commit()
        log_event("Admin", f"Denied account request {req['requested_username']}")
        log_security_event("account_request_denied", req["requested_username"], "Denied by owner/admin", "WARN")
        try:
            from app.application_notifications import notify_requester_account_decision

            n_ok, n_msg = notify_requester_account_decision(
                db(), req_id, "Denied", request_base_url=request.url_root.rstrip("/")
            )
            flash("Account request denied." + (f" Requester emailed." if n_ok else f" ({n_msg})"), "success")
        except Exception as exc:
            flash(f"Account request denied. Email notify error: {exc}", "warning")
    return redirect(url_for("admin"))
@app.route("/admin/revoke/<sid>")
@login_required("view_admin")
def revoke_session(sid: str):
    db().execute("UPDATE online_sessions SET revoked=1, active=0, revoke_reason=? WHERE session_id=?", (f"Revoked by {session.get('username')}", sid))
    db().commit(); log_event("Admin", f"Revoked session {sid}"); flash("Session ended.", "success");     return redirect(url_for("admin"))
@app.route("/admin/user/<int:user_id>/role", methods=["POST"])
@login_required("manage_users")
def quick_change_user_role(user_id: int):
    if not is_admin_role(session.get("role", "")):
        log_security_event("role_change_denied", session.get("username", ""), "Non-admin attempted account type change", "WARN")
        abort(403)
    user = db().execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        abort(404)
    new_role = request.form.get("role") or user["role"]
    conn = db()
    ok, msg = apply_user_role_change(conn, user, new_role, session.get("username", ""))
    if not ok:
        flash(msg, "error")
        return redirect(url_for("admin"))
    if msg == "unchanged":
        flash(f"No change — {user['username']} is already {role_display(user['role'])}.", "warning")
    else:
        conn.commit()
        log_event("Admin", msg)
        flash(msg, "success")
    return redirect(url_for("admin"))
@app.route("/admin/new_user", methods=["GET", "POST"])
@login_required("manage_users")
def new_user():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role") or "viewer"
        if not username or not password:
            flash("Username and password required.", "error")
        elif role not in ROLE_LABELS:
            flash("Invalid role.", "error")
        elif role == "admin":
            flash("Cannot create admin accounts here. Use owner first-setup or emergency mastery access.", "error")
        else:
            ok, msg = enforce_new_password_policy(password, role=role)
            if not ok:
                flash(msg, "error")
            else:
                try:
                    salt, ph = hash_password(password)
                    db().execute("INSERT INTO users (username,display_name,role,salt,password_hash,active,must_change_password,created_at,notes) VALUES (?,?,?,?,?,1,1,?,?)", (username, request.form.get("display_name"), role, salt, ph, now_iso(), request.form.get("notes")))
                    user_id = db().execute("SELECT last_insert_rowid()").fetchone()[0]
                    from app.account_provisioning import provision_user_role_profiles
                    provision_user_role_profiles(db(), user_id, username, role)
                    db().commit(); log_event("Admin", f"Created user {username} role {role}"); flash("User added.", "success"); return redirect(url_for("admin"))
                except sqlite3.IntegrityError:
                    flash("Username already exists.", "error")
    role_opts = role_select_options(exclude=("admin",))
    body = f"""<div class="card"><h2>Add User</h2><form method="post"><div class="row3"><p><label>Username</label><input name="username"></p><p><label>Display Name</label><input name="display_name"></p><p><label>Account Type</label><select name="role">{role_opts}</select></p></div><p><label>Temporary Password</label><input name="password" type="password"></p><p><label>Notes</label><textarea name="notes"></textarea></p><button>Add User</button></form></div>"""
    return layout("Add User", body, "admin")
@app.route("/admin/user/<int:user_id>", methods=["GET", "POST"])
@login_required("manage_users")
def edit_user(user_id: int):
    user = db().execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user: abort(404)
    if request.method == "POST":
        role = request.form.get("role") or user["role"]
        active = 1 if request.form.get("active") == "on" else 0
        conn = db()
        ok_role, role_msg = apply_user_role_change(
            conn, user, role, session.get("username", ""), mastery_key=request.form.get("mastery_key", "")
        )
        if not ok_role:
            flash(role_msg, "error")
            return redirect(url_for("edit_user", user_id=user_id))
        db().execute(
            "UPDATE users SET display_name=?, active=?, notes=?, email=?, recovery_email=?, phone=?, title=?, last_profile_update=? WHERE id=?",
            (request.form.get("display_name"), active, request.form.get("notes"), request.form.get("email"),
             request.form.get("recovery_email"), request.form.get("phone"), request.form.get("title"), now_iso(), user_id),
        )
        if request.form.get("new_password"):
            mastery = request.form.get("mastery_key", "").strip()
            ok, msg = enforce_new_password_policy(request.form.get("new_password"), mastery)
            if not ok:
                flash(msg, "error")
                return redirect(url_for("edit_user", user_id=user_id))
            salt, ph = hash_password(request.form.get("new_password"))
            db().execute("UPDATE users SET salt=?, password_hash=?, must_change_password=1 WHERE id=?", (salt, ph, user_id))
        db().commit()
        log_event("Admin", f"Updated user {user['username']}" + (f"; {role_msg}" if role_msg != "unchanged" else ""))
        flash("User updated." + (f" {role_msg}" if role_msg != "unchanged" else ""), "success")
        return redirect(url_for("admin"))
    role_opts = role_select_options(user["role"])
    role_help = "<br>".join(f"<span class='muted'><b>{html.escape(ROLE_DISPLAY_NAMES.get(r, r))}</b> — {permission_badges(r)}</span>" for r in ROLE_LABELS if r == normalize_role_for_session(user["role"] or ""))
    body = f"""<div class="card"><h2>Edit User: {html.escape(user['username'])}</h2>
    <p class='muted'>Current account type: <b>{html.escape(role_display(user['role']))}</b>. Changing type updates permissions immediately. Promoting to Owner/Admin requires mastery key below.</p>
    <form method="post"><div class="row3"><p><label>Display Name</label><input name="display_name" value="{html.escape(user['display_name'] or '')}"></p><p><label>Account Type</label><select name="role">{role_opts}</select></p><p><label>Active</label><input type="checkbox" name="active" {'checked' if user['active'] else ''}></p></div>
    <p>{role_help}</p>
    <div class='row3'><p><label>Email</label><input name='email' value="{html.escape(user['email'] or '')}"></p><p><label>Recovery Email</label><input name='recovery_email' value="{html.escape(user['recovery_email'] or '')}"></p><p><label>Phone</label><input name='phone' value="{html.escape(user['phone'] or '')}"></p></div><p><label>Title / Worker Type</label><input name='title' value="{html.escape(user['title'] or '')}"></p><p><label>Reset Password</label><input name="new_password" type="password" placeholder="Leave blank to keep current"></p><p><label>Mastery key (Owner/Admin promotion or ivygrows reset)</label><input name="mastery_key" type="password" autocomplete="off"></p><p><label>Notes</label><textarea name="notes">{html.escape(user['notes'] or '')}</textarea></p><button>Save</button> <a class='btn btn2' href='/admin'>Back to Admin</a></form></div>"""
    return layout("Edit User", body, "admin")
@app.route("/admin/export_users")
@login_required("view_admin")
def export_users():
    path = EXPORT_DIR / "JRC_User_Accounts_Admin_Index.csv"
    rows = db().execute("SELECT username, display_name, role, active, must_change_password, created_at, last_login, last_ip_address, email, phone, title, notes FROM users ORDER BY username").fetchall()
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["username", "display_name", "role", "active", "must_change_password", "created_at", "last_login", "last_ip_address", "email", "phone", "title", "notes", "password_storage"])
        for r in rows:
            writer.writerow([r["username"], r["display_name"], r["role"], r["active"], r["must_change_password"], r["created_at"], r["last_login"], r["last_ip_address"], r["email"], r["phone"], r["title"], r["notes"], "hashed in SQLite - not exported"])
    log_event("Admin", "Exported user account index")
    return send_file(path, as_attachment=True)


@app.route("/admin/troubleshooter", methods=["GET", "POST"])
@login_required("view_admin")
def admin_troubleshooter_page():
    _require_admin_role()
    from app.troubleshooter_engine import format_steps_html, run_full_troubleshoot

    steps = []
    report_name = ""
    if request.method == "POST":
        action = request.form.get("action", "repair")
        repair = action != "check"
        try:
            report_path, steps = run_full_troubleshoot(repair=repair)
            report_name = report_path.name
            log_event("Admin", f"Troubleshooter ({'repair' if repair else 'check'}): {report_name}")
            flash(f"Troubleshooter complete. Report: {report_name}", "success")
        except Exception as exc:
            flash(f"Troubleshooter error: {exc}", "error")

    rows = format_steps_html(steps)
    body = f"""
    <div class="card"><h2>Full Troubleshooter</h2>
      <p class="muted">Checks and safely repairs launchers, Python packages, database, shortcuts, shared host, Densus link, data pipeline, and health — all in one place.</p>
      <form method="post" style="display:inline;margin-right:10px">
        <input type="hidden" name="action" value="repair">
        <button type="submit">Run Auto-Repair (fix safe issues)</button>
      </form>
      <form method="post" style="display:inline;margin-right:10px">
        <input type="hidden" name="action" value="check">
        <button type="submit" class="btn btn2">Check Only (no changes)</button>
      </form>
      <a class="btn btn2" href="/admin">Back to Admin</a>
      <p class="muted" style="margin-top:10px">Reports save to <code>exports\\JRC_Full_Troubleshooter_*.txt</code></p>
    </div>
    <div class="card"><h2>Results</h2>
      <table><tr><th>Status</th><th>Category</th><th>Check</th><th>Detail</th></tr>{rows}</table>
    </div>"""
    return layout("Troubleshooter", body, "admin")


def _admin_troubleshooter_redirect(mode: str):
    from app.troubleshooter_engine import run_full_troubleshoot
    try:
        repair = mode == "repair"
        report_path, _ = run_full_troubleshoot(repair=repair)
        log_event("Admin", f"Troubleshooter: {report_path.name}")
        flash(f"Troubleshooter complete. Report: {report_path.name}", "success")
    except Exception as exc:
        flash(f"Troubleshooter error: {exc}", "error")
    return redirect(url_for("admin_troubleshooter_page"))


@app.route("/admin/run-troubleshooter", methods=["POST"])
@login_required("view_admin")
def admin_run_troubleshooter():
    _require_admin_role()
    return _admin_troubleshooter_redirect("check")


@app.route("/admin/run-auto-repair", methods=["POST"])
@login_required("view_admin")
def admin_run_auto_repair():
    _require_admin_role()
    return _admin_troubleshooter_redirect("repair")


@app.route("/admin/fix-launchers", methods=["POST"])
@login_required("view_admin")
def admin_fix_launchers():
    _require_admin_role()
    try:
        from app.launcher_repair import repair_launcher_files, verify_app_imports
        actions = repair_launcher_files()
        ok, msg = verify_app_imports()
        if not ok:
            from app.troubleshooter_engine import check_dependencies
            check_dependencies(repair=True)
            ok, msg = verify_app_imports()
        log_event("Admin", f"Launcher repair; import={'OK' if ok else 'FAIL'}")
        flash(("Fixed: " + "; ".join(actions[:2]) + f" — {msg}")[:450], "success" if ok else "warning")
    except Exception as exc:
        flash(f"Launcher repair error: {exc}", "error")
    return redirect(url_for("admin"))


def run_health_checks() -> List[Tuple[str, str, str]]:
    results = []
    try:
        with direct_db() as conn:
            conn.execute("SELECT 1").fetchone()
            results.append(("OK", "Database", "SQLite database opened successfully."))
            admin = conn.execute("SELECT * FROM users WHERE username='admin'").fetchone()
            if admin and verify_password("admin", admin["salt"], admin["password_hash"]):
                results.append(("WARN", "Security", "Default admin/admin password is still active. Change it."))
            else:
                results.append(("OK", "Security", "Default admin password is not active."))
            if PUBLIC_HOST_MODE and admin and verify_password("admin", admin["salt"], admin["password_hash"]):
                results.append(("ERROR", "Hosted Security", "Public host mode should not run with default admin/admin."))
            if PUBLIC_HOST_MODE:
                results.append(("WARN", "Hosted Mode", "Public host mode requires HTTPS/proxy/firewall outside this Python app."))
            else:
                results.append(("OK", "Hosted Mode", "LAN/VPN mode active."))
            missing = []
            for folder in [DATA_DIR, EXPORT_DIR, EVIDENCE_DIR, CHATGPT_IMPORTS_DIR, BACKUP_DIR]:
                if not folder.exists():
                    folder.mkdir(parents=True, exist_ok=True)
                    missing.append(str(folder))
            if missing:
                results.append(("FIXED", "Folders", "Created missing folders: " + ", ".join(missing)))
            else:
                results.append(("OK", "Folders", "Required folders exist."))
            sources = conn.execute("SELECT folder_path FROM file_sources WHERE active=1").fetchall()
            missing_sources = [s["folder_path"] for s in sources if not Path(s["folder_path"]).exists()]
            if missing_sources:
                results.append(("WARN", "File Sources", "Missing source folders: " + "; ".join(missing_sources[:5])))
            else:
                results.append(("OK", "File Sources", "All active source folders are reachable."))
            quick = conn.execute("PRAGMA quick_check").fetchone()[0]
            if str(quick).lower() == "ok":
                results.append(("OK", "Database Integrity", "SQLite quick_check passed."))
            else:
                results.append(("ERROR", "Database Integrity", "SQLite quick_check returned: " + str(quick)))
            backups = len(list(BACKUP_DIR.glob("*.zip"))) if BACKUP_DIR.exists() else 0
            if backups == 0:
                results.append(("WARN", "Backups", "No local backup ZIPs found. Create a backup before heavy use."))
            else:
                results.append(("OK", "Backups", f"{backups} backup ZIP(s) available."))
            conn.execute("CREATE TABLE IF NOT EXISTS security_events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_time TEXT, level TEXT, event_type TEXT, username TEXT, ip_address TEXT, user_agent TEXT, message TEXT)")
            sec_count = conn.execute("SELECT COUNT(*) FROM security_events").fetchone()[0]
            results.append(("OK", "Security Events", f"Security/account event table ready with {sec_count} event(s)."))
            pending_requests = conn.execute("SELECT COUNT(*) FROM account_requests WHERE status='Pending'").fetchone()[0] if 'account_requests' in {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()} else 0
            if pending_requests:
                results.append(("WARN", "Account Requests", f"{pending_requests} pending account request(s) waiting for admin approval."))
            else:
                results.append(("OK", "Account Requests", "No pending account requests."))
            stale = conn.execute("SELECT COUNT(*) FROM online_sessions WHERE active=1 AND last_seen < ?", ((dt.datetime.now() - dt.timedelta(minutes=SESSION_TIMEOUT_MINUTES)).isoformat(timespec="seconds"),)).fetchone()[0]
            if stale:
                cleanup_stale_sessions(); results.append(("FIXED", "Sessions", f"Cleaned up {stale} stale session(s)."))
            else:
                results.append(("OK", "Sessions", "No stale active sessions found."))
    except Exception as exc:
        results.append(("ERROR", "Health", str(exc)))
    for level, component, message in results:
        health_event(level, component, message, 1 if level == "FIXED" else 0)
    return results
@app.route("/remote-mobile", methods=["GET", "POST"])
@login_required("configure_hosting")
def remote_mobile_access():
    init_db()
    local_base = f"http://127.0.0.1:{int(os.environ.get('JRC_PORT','8765'))}"
    lan_base = f"http://{get_lan_ip()}:{int(os.environ.get('JRC_PORT','8765'))}"
    current_remote = get_app_setting("remote_public_base_url", "")
    if request.method == "POST":
        remote_url = clean_base_url(request.form.get("remote_public_base_url", ""))
        set_app_setting("remote_public_base_url", remote_url)
        set_app_setting("remote_mobile_updated_at", now_iso())
        try:
            from app.cloud_url_sync import sync_cloud_url
            sync_cloud_url(remote_url)
        except Exception:
            pass
        log_event("Remote Mobile", f"Remote mobile base URL updated to {remote_url or 'blank'}")
        flash("Remote mobile URL setting saved. Use HTTPS/VPN/tunnel for outside access.", "success")
        return redirect(url_for("remote_mobile_access"))
    remote_base = current_remote or ""
    def link_block(label, base):
        if not base:
            return f"<div class='stat'>{label}<b>Not set</b><span class='muted'>Configure a secure tunnel/VPN/cloud URL first.</span></div>"
        return f"""<div class='stat'>{label}<b>{html.escape(base)}</b>
        <span class='muted'>Mobile: <code>{html.escape(access_url(base,'/mobile'))}</code><br>
        Account request: <code>{html.escape(access_url(base,'/register'))}</code><br>
        Job application: <code>{html.escape(access_url(base,'/apply'))}</code></span></div>"""
    body = f"""
    <div class='card'><h2>Remote Mobile Access</h2>
      <p>This page helps you use J and R Construction Manager from phones or tablets outside the jobsite/home Wi-Fi.</p>
      <p><b>Safe rule:</b> do not open your laptop directly to the public internet. Use a secure VPN/tunnel or a cloud/VPS host with HTTPS.</p>
      <p class='muted'>Remote users do not install the desktop program. They open your shared link in a browser, then log in or submit an application/account request.</p>
    </div>
    <div class='grid'>
      {link_block('Local computer', local_base)}
      {link_block('Same Wi-Fi / LAN', lan_base)}
      {link_block('Remote secure URL', remote_base)}
    </div>
    <div class='card'><h2>Set Remote Public/Secure URL</h2>
      <form method='post'>
        <label>Remote HTTPS/VPN/tunnel base URL</label>
        <input name='remote_public_base_url' value='{html.escape(remote_base)}' placeholder='https://your-secure-host-or-tunnel.example.com'>
        <p class='muted'>Examples: a Cloudflare Tunnel URL, Tailscale/VPN address, or your future cloud/VPS domain. HTTPS is recommended for secure cookies and remote use.</p>
        <button>Save Remote URL</button>
      </form>
    </div>
    <div class='row'>
      <div class='card'><h2>Remote Links to Share</h2>
        <p><b>Mobile App:</b><br><code>{html.escape(access_url(remote_base,'/mobile') if remote_base else 'Set remote URL first')}</code></p>
        <p><b>New Account Request:</b><br><code>{html.escape(access_url(remote_base,'/register') if remote_base else 'Set remote URL first')}</code></p>
        <p><b>Job / Worker Application:</b><br><code>{html.escape(access_url(remote_base,'/apply') if remote_base else 'Set remote URL first')}</code></p>
      </div>
      <div class='card'><h2>Best Remote Setup Options</h2>
        <ol>
          <li><b>Best for testing:</b> same Wi-Fi/LAN using the LAN URL above.</li>
          <li><b>Best for outside access without cloud:</b> VPN or secure tunnel. Keep laptop on.</li>
          <li><b>Best long-term:</b> cloud/VPS Docker host with HTTPS, backups, firewall, and strong passwords.</li>
        </ol>
      </div>
    </div>
    <div class='card'><h2>Remote Security Checklist</h2>
      <ul>
        <li>Change default admin/admin password before sharing any remote link.</li>
        <li>Use HTTPS for remote access so browser session and device cookies can use Secure mode.</li>
        <li>Use worker/viewer roles for read-only users.</li>
        <li>Approve account requests manually from the Admin panel.</li>
        <li>Use System Check after changing host mode or remote URL.</li>
      </ul>
    </div>
    """
    return layout("Remote Mobile Access", body, "remote")
@app.route("/hosting")
@login_required("manage_settings")
def hosting():
    cleanup_count = cleanup_stale_sessions()
    lan_ip = get_lan_ip()
    port = int(os.environ.get("JRC_PORT", "8765"))
    public_mode = "Enabled" if PUBLIC_HOST_MODE else "Off"
    sessions = db().execute("SELECT COUNT(*) FROM online_sessions WHERE active=1 AND revoked=0").fetchone()[0]
    events = db().execute("SELECT * FROM host_events ORDER BY id DESC LIMIT 50").fetchall()
    event_rows = ''.join(f"<tr><td>{html.escape(r['event_time'])}</td><td>{html.escape(r['level'])}</td><td>{html.escape(r['host_mode'] or '')}</td><td>{html.escape(r['message'] or '')}</td><td>{html.escape(r['ip_address'] or '')}</td><td>{html.escape(r['username'] or '')}</td></tr>" for r in events)
    try:
        from app.data_pipeline import mode_label, resolve_paths
        pl = resolve_paths()
        pipeline_card = f"""<div class="card"><h2>Data Pipeline</h2>
      <p><b>Mode:</b> {html.escape(pl.mode)} — {html.escape(mode_label())}</p>
      <p><b>Authority:</b> {html.escape(pl.data_authority)}</p>
      <p><b>Database:</b> <code>{html.escape(str(pl.db_path))}</code></p>
      <p><b>Sessions archive:</b> <code>{html.escape(str(pl.sessions_archive_dir))}</code></p>
      <p class="muted">Master PC stores live DB + session snapshots locally. Cloud uses JRC_DATA_DIR on server volume. Worker PCs store nothing.</p></div>"""
    except Exception:
        pipeline_card = ""
    body = f"""
    <div class="grid">
      <div class="stat">Server Mode<b>{'Public/Hosted' if PUBLIC_HOST_MODE else 'Local/LAN'}</b><span class="muted">PUBLIC_HOST_MODE={public_mode}</span></div>
      <div class="stat">Local URL<b>127.0.0.1:{port}</b></div>
      <div class="stat">LAN URL<b>{lan_ip}:{port}</b></div>
      <div class="stat">Active Sessions<b>{sessions}</b><span class="muted">Cleaned stale: {cleanup_count}</span></div>
    </div>
    {pipeline_card}
    <div class="card"><h2>Best Hosting Path</h2>
      <p><b>Most secure for now:</b> Jacob's administrator laptop hosting on trusted LAN or VPN only.</p>
      <p><b>Best future internet host:</b> a dedicated cloud/VPS server or managed app host with HTTPS, backups, firewall rules, and a real domain. Do not expose the laptop server directly to the open internet.</p>
      <p><b>Safe outside access option:</b> host behind a VPN or tunnel provider and only allow invited users. Change admin/admin before using outside your home network.</p>
    </div>
    <div class="card"><h2>Shared Session Checks</h2>
      <ul><li>Sessions expire after {SESSION_TIMEOUT_MINUTES} minutes of inactivity.</li><li>Admins can revoke sessions from the Admin panel.</li><li>Passwords are hashed in SQLite.</li><li>Business events and host events are timestamped.</li><li>File refresh scans local Dropbox-sync folders, program evidence, exports, and ChatGPT imports.</li></ul>
    </div>
    <div class="card"><h2>Hosting Tools</h2>
      <p><a class="btn" href="/api/health">API Health</a> <a class="btn btn2" href="/health/run">Run Full Health Check</a> <a class="btn btn2" href="/backup">Create Backup ZIP</a></p>
    </div>
    <div class="card"><h2>Recent Host Events</h2><table><tr><th>Time</th><th>Level</th><th>Mode</th><th>Message</th><th>IP</th><th>User</th></tr>{event_rows}</table></div>
    """
    host_event("INFO", "public" if PUBLIC_HOST_MODE else "lan", "Viewed hosting dashboard")
    return layout("Hosting", body, "hosting")
@app.route("/api/sessions")
@login_required("view_admin")
def api_sessions():
    rows = db().execute("SELECT username, role, ip_address, login_time, last_seen, active, revoked FROM online_sessions ORDER BY last_seen DESC LIMIT 200").fetchall()
    return jsonify([dict(r) for r in rows])
def data_status_snapshot() -> Dict[str, Any]:
    conn = db()
    snapshot: Dict[str, Any] = {}
    snapshot["jobs"] = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    snapshot["expenses"] = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    snapshot["workers"] = conn.execute("SELECT COUNT(*) FROM workers").fetchone()[0]
    snapshot["worker_payments"] = conn.execute("SELECT COUNT(*) FROM worker_payments").fetchone()[0]
    snapshot["payroll_periods"] = conn.execute("SELECT COUNT(*) FROM payroll_periods").fetchone()[0]
    snapshot["invoices"] = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    snapshot["file_sources"] = conn.execute("SELECT COUNT(*) FROM file_sources WHERE active=1").fetchone()[0]
    snapshot["indexed_files"] = conn.execute("SELECT COUNT(*) FROM file_index").fetchone()[0]
    snapshot["open_conflicts"] = conn.execute("SELECT COUNT(*) FROM data_conflicts WHERE status='Open'").fetchone()[0]
    snapshot["backups"] = len(list(BACKUP_DIR.glob("*.zip"))) if BACKUP_DIR.exists() else 0
    snapshot["db_size"] = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    try:
        snapshot["db_quick_check"] = conn.execute("PRAGMA quick_check").fetchone()[0]
    except Exception as exc:
        snapshot["db_quick_check"] = str(exc)
    try:
        from app.mobile_pipeline import pipeline_api_payload
        snapshot["pipeline"] = pipeline_api_payload(conn)
    except Exception:
        snapshot["pipeline"] = {}
    return snapshot
def detect_data_conflicts() -> List[str]:
    conn = db()
    warnings: List[str] = []
    duplicate_jobs = conn.execute("SELECT lower(trim(job_name)) AS k, COUNT(*) c FROM jobs GROUP BY k HAVING c > 1").fetchall()
    for row in duplicate_jobs:
        msg = f"Duplicate job name detected: {row['k']} appears {row['c']} times"
        warnings.append(msg)
        conn.execute("INSERT INTO data_conflicts (detected_at, conflict_type, source_a, source_b, notes) VALUES (?,?,?,?,?)", (now_iso(), "Duplicate Job", "jobs", "jobs", msg))
    duplicate_files = conn.execute("SELECT lower(file_name) AS k, COUNT(*) c FROM file_index GROUP BY k HAVING c > 1 LIMIT 25").fetchall()
    for row in duplicate_files:
        msg = f"Multiple indexed files share a name: {row['k']} appears {row['c']} times"
        warnings.append(msg)
        conn.execute("INSERT INTO data_conflicts (detected_at, conflict_type, source_a, source_b, notes) VALUES (?,?,?,?,?)", (now_iso(), "Duplicate File Name", "file_index", "file_index", msg))
    conn.commit()
    return warnings
def full_data_refresh(run_type: str = "manual") -> Tuple[int, int, int, List[str]]:
    conn = db()
    source_count = conn.execute("SELECT COUNT(*) FROM file_sources WHERE active=1").fetchone()[0]
    notes: List[str] = []
    counts = scan_sources()
    errors = int(counts.get("errors", 0))
    indexed_after = conn.execute("SELECT COUNT(*) FROM file_index").fetchone()[0]
    notes.append(f"Scanned {counts.get('files', 0)} files from {counts.get('sources', 0)} active sources")
    conflicts = detect_data_conflicts()
    warnings = len(conflicts)
    notes.extend(conflicts[:10])
    missing_sources = conn.execute("SELECT label, folder_path FROM file_sources WHERE active=1").fetchall()
    for src in missing_sources:
        if not Path(src["folder_path"]).expanduser().exists():
            warnings += 1
            notes.append(f"Missing source: {src['label']} -> {src['folder_path']}")
    conn.execute("INSERT INTO data_refresh_runs (run_time, run_type, source_count, files_indexed, warnings, errors, notes, username) VALUES (?,?,?,?,?,?,?,?)", (now_iso(), run_type, source_count, indexed_after, warnings, errors, " | ".join(notes[:20]), session.get("username", "system")))
    conn.commit()
    log_event("Data Refresh", f"{run_type} refresh: {indexed_after} indexed files, {warnings} warnings, {errors} errors")
    return indexed_after, warnings, errors, notes
def create_diagnostic_report() -> Path:
    snap = data_status_snapshot()
    out = EXPORT_DIR / f"JRC_Diagnostic_Report_{dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.txt"
    recent_health = db().execute("SELECT * FROM health_events ORDER BY id DESC LIMIT 25").fetchall()
    recent_refresh = db().execute("SELECT * FROM data_refresh_runs ORDER BY id DESC LIMIT 10").fetchall()
    lines = [
        f"{APP_NAME} Diagnostic Report",
        f"Version: {APP_VERSION}",
        f"Business: {BUSINESS_NAME}",
        f"Owner: {OWNER}",
        f"Created: {now_iso()}",
        "",
        "DATA STATUS",
    ]
    for k, v in snap.items():
        lines.append(f"- {k}: {v}")
    lines.append("\nRECENT HEALTH EVENTS")
    for r in recent_health:
        lines.append(f"- {r['event_time']} [{r['level']}] {r['component']}: {r['message']}")
    lines.append("\nRECENT DATA REFRESH RUNS")
    for r in recent_refresh:
        lines.append(f"- {r['run_time']} {r['run_type']}: files={r['files_indexed']} warnings={r['warnings']} errors={r['errors']} notes={r['notes']}")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
@app.route("/data")
@login_required("audit")
def data_management():
    snap = data_status_snapshot()
    runs = db().execute("SELECT * FROM data_refresh_runs ORDER BY id DESC LIMIT 25").fetchall()
    conflicts = db().execute("SELECT * FROM data_conflicts ORDER BY id DESC LIMIT 50").fetchall()
    run_rows = ''.join(f"<tr><td>{html.escape(r['run_time'] or '')}</td><td>{html.escape(r['run_type'] or '')}</td><td>{r['source_count']}</td><td>{r['files_indexed']}</td><td>{r['warnings']}</td><td>{r['errors']}</td><td>{html.escape(r['notes'] or '')}</td></tr>" for r in runs)
    conflict_rows = ''.join(f"<tr><td>{html.escape(r['detected_at'] or '')}</td><td>{html.escape(r['conflict_type'] or '')}</td><td>{html.escape(r['status'] or '')}</td><td>{html.escape(r['notes'] or '')}</td></tr>" for r in conflicts)
    body = f"""
    <div class="grid">
      <div class="stat">Jobs<b>{snap['jobs']}</b></div>
      <div class="stat">Expenses<b>{snap['expenses']}</b></div>
      <div class="stat">Indexed Files<b>{snap['indexed_files']}</b></div>
      <div class="stat">Backups<b>{snap['backups']}</b></div>
      <div class="stat">DB Check<b>{html.escape(str(snap['db_quick_check']))}</b></div>
      <div class="stat">Open Conflicts<b>{snap['open_conflicts']}</b></div>
    </div>
    <div class="card"><h2>Data Controls</h2><p>This keeps the manager current from local program data, evidence, exports, ChatGPT imports, and local Dropbox-sync folders you add.</p>
      <p><a class="btn" href="/data/refresh">Refresh and Analyze Sources</a> <a class="btn btn2" href="/health/run">Run Repair Checks</a> <a class="btn btn2" href="/backup">Create Backup ZIP</a> <a class="btn btn2" href="/data/diagnostic">Download Diagnostic Report</a></p>
    </div>
    <div class="card"><h2>Recent Refresh Runs</h2><table><tr><th>Time</th><th>Type</th><th>Sources</th><th>Indexed Files</th><th>Warnings</th><th>Errors</th><th>Notes</th></tr>{run_rows}</table></div>
    <div class="card"><h2>Open / Recent Conflicts</h2><table><tr><th>Detected</th><th>Type</th><th>Status</th><th>Notes</th></tr>{conflict_rows}</table></div>
    """
    return layout("Data Management", body, "data")
@app.route("/data/refresh")
@login_required("manage_files")
def data_refresh_route():
    count, warnings, errors, notes = full_data_refresh("manual")
    flash(f"Refresh complete. Indexed files: {count}. Warnings: {warnings}. Errors: {errors}.", "success" if errors == 0 else "warning")
    return redirect(url_for("data_management"))
@app.route("/data/diagnostic")
@login_required("audit")
def data_diagnostic():
    path = create_diagnostic_report()
    log_event("Troubleshooting", f"Created diagnostic report {path.name}")
    return send_file(path, as_attachment=True)
@app.route("/api/cloud-readiness")
@login_required("manage_settings")
def api_cloud_readiness():
    required = ["cloud_hosting/README_CLOUD_HOSTING_JRC.txt", "cloud_hosting/Dockerfile", "cloud_hosting/docker-compose.yml", "cloud_hosting/Procfile", "cloud_hosting/render.yaml", "cloud_hosting/cloud_entry.py"]
    missing = [rel for rel in required if not (BASE_DIR / rel).exists()]
    return jsonify({"status": "ok" if not missing else "missing_files", "missing": missing, "public_host_mode": PUBLIC_HOST_MODE, "base_dir": str(BASE_DIR), "recommendation": "Use cloud/VPS/tunnel with HTTPS for remote locations; use local host for same-Wi-Fi/VPN only."})
@app.route("/cloud")
@login_required("manage_settings")
def cloud_setup():
    profiles = db().execute("SELECT * FROM cloud_profiles ORDER BY id DESC").fetchall()
    if not profiles:
        db().execute("INSERT OR IGNORE INTO cloud_profiles (profile_name, host_type, status, notes, created_at, updated_at) VALUES (?,?,?,?,?,?)", ("Local Administrator Laptop", "LAN host", "Ready", "Best immediate option. Use trusted LAN or VPN.", now_iso(), now_iso()))
        db().execute("INSERT OR IGNORE INTO cloud_profiles (profile_name, host_type, status, notes, created_at, updated_at) VALUES (?,?,?,?,?,?)", ("Docker VPS / Cloud Server", "Cloud VPS", "Template included", "Use Docker, HTTPS reverse proxy, firewall, domain, strong admin password, backups.", now_iso(), now_iso()))
        db().execute("INSERT OR IGNORE INTO cloud_profiles (profile_name, host_type, status, notes, created_at, updated_at) VALUES (?,?,?,?,?,?)", ("Secure Tunnel / VPN", "Tunnel/VPN", "Planned", "Safer than opening router ports. Use invited users only.", now_iso(), now_iso()))
        db().commit()
        profiles = db().execute("SELECT * FROM cloud_profiles ORDER BY id DESC").fetchall()
    rows = ''.join(f"<tr><td>{html.escape(r['profile_name'] or '')}</td><td>{html.escape(r['host_type'] or '')}</td><td>{html.escape(r['status'] or '')}</td><td>{html.escape(r['base_url'] or '')}</td><td>{html.escape(r['notes'] or '')}</td></tr>" for r in profiles)
    body = f"""
    <div class="card"><h2>Cloud Hosting Options</h2><p><b>Local laptop hosting is optional and only recommended for same-Wi-Fi or VPN testing.</b> For real remote mobile access from other locations, use a cloud/VPS/tunnel setup with HTTPS. This avoids Windows Firewall, router/NAT, sleep mode, changing IP addresses, and heavy local background processes.</p><p><a class="btn" href="/api/cloud-readiness">Cloud Readiness API</a> <a class="btn btn2" href="/connect">Connection Test</a></p></div>
    <div class="grid">
      <div class="stat">Local/LAN Host<b>Ready</b><span class="muted">Use START_BEST_HOST_SERVER.bat</span></div>
      <div class="stat">Secure Tunnel/VPN<b>Supported</b><span class="muted">Use public mode only behind protection</span></div>
      <div class="stat">Cloud/VPS Docker<b>Templates</b><span class="muted">Dockerfile, compose, nginx, backup scripts included</span></div>
    </div>
    <div class="card"><h2>Profiles</h2><table><tr><th>Name</th><th>Type</th><th>Status</th><th>URL</th><th>Notes</th></tr>{rows}</table></div>
    <div class="card"><h2>Checks and Balances</h2><ul><li>Never run internet/public mode with admin/admin.</li><li>Use HTTPS and firewall rules before letting outside users connect.</li><li>Keep Dropbox as evidence/source storage, not as a live shared SQLite database.</li><li>Back up before every update and before major imports.</li><li>Use the Admin panel to remove inactive users and revoke sessions.</li></ul></div>
    """
    return layout("Cloud Setup", body, "cloud")
@app.route("/sharing", methods=["GET", "POST"])
@login_required(any_permission=("view_shared_sessions", "view_customer_shared"))
def sharing_center():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "share_file" and has_permission_role(session.get("role"), "share_files"):
            file_id = int(request.form.get("file_index_id") or 0)
            r = db().execute("SELECT * FROM file_index WHERE id=?", (file_id,)).fetchone()
            if r:
                db().execute("INSERT INTO shared_files (file_index_id,file_path,file_name,shared_by_user_id,shared_by_username,shared_with_role,share_note,created_at,active) VALUES (?,?,?,?,?,?,?,?,1)",
                             (file_id, r["file_path"], r["file_name"], session.get("user_id"), session.get("username"), request.form.get("shared_with_role") or "viewer", request.form.get("share_note"), now_iso()))
                db().commit(); log_event("Sharing", f"Shared file {r['file_name']}"); flash("File shared.", "success")
        elif action == "share_job" and has_permission_role(session.get("role"), "share_jobs"):
            job_id = int(request.form.get("job_id") or 0)
            r = db().execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if r:
                db().execute("INSERT INTO shared_jobs (job_id,shared_by_user_id,shared_by_username,shared_with_role,share_note,created_at,active) VALUES (?,?,?,?,?,?,1)",
                             (job_id, session.get("user_id"), session.get("username"), request.form.get("shared_with_role") or "viewer", request.form.get("share_note"), now_iso()))
                db().commit(); log_event("Sharing", f"Shared job {r['job_name']}"); flash("Job shared.", "success")
        return redirect(url_for("sharing_center"))
    role = session.get("role") or "viewer"
    files = db().execute("SELECT id,file_name,analysis FROM file_index ORDER BY discovered_at DESC LIMIT 100").fetchall() if has_permission_role(role, "share_files") else []
    jobs_rows = db().execute("SELECT id,job_name,status FROM jobs ORDER BY updated_at DESC, id DESC LIMIT 100").fetchall() if has_permission_role(role, "share_jobs") else []
    all_shared_files = db().execute("SELECT * FROM shared_files WHERE active=1 ORDER BY id DESC LIMIT 100").fetchall()
    all_shared_jobs = db().execute("SELECT sj.*, j.job_name FROM shared_jobs sj LEFT JOIN jobs j ON j.id=sj.job_id WHERE sj.active=1 ORDER BY sj.id DESC LIMIT 100").fetchall()
    shared_files = [r for r in all_shared_files if role_can_access_share(role, r["shared_with_role"] or "viewer")]
    shared_jobs = [r for r in all_shared_jobs if role_can_access_share(role, r["shared_with_role"] or "viewer")]
    online = db().execute("SELECT username,role,ip_address,login_time,last_seen FROM online_sessions WHERE active=1 AND revoked=0 ORDER BY last_seen DESC").fetchall() if has_permission_role(role, "view_admin") else []
    role_opts = ''.join(f'<option value="{r}">{r}</option>' for r in ROLE_LABELS)
    file_opts = ''.join(f'<option value="{f["id"]}">{html.escape(f["file_name"])}</option>' for f in files)
    job_opts = ''.join(f'<option value="{j["id"]}">{html.escape(j["job_name"])} - {html.escape(j["status"] or "")}</option>' for j in jobs_rows)
    sf_rows = ''.join(f"<tr><td>{html.escape(r['file_name'] or '')}</td><td>{html.escape(r['shared_with_role'] or '')}</td><td>{html.escape(r['shared_by_username'] or '')}</td><td>{html.escape(r['created_at'] or '')}</td><td>{html.escape(r['share_note'] or '')}</td><td><a href='/shared/file/{r['id']}'>Open</a></td></tr>" for r in shared_files)
    sj_rows = ''.join(f"<tr><td>{html.escape(r['job_name'] or '')}</td><td>{html.escape(r['shared_with_role'] or '')}</td><td>{html.escape(r['shared_by_username'] or '')}</td><td>{html.escape(r['created_at'] or '')}</td><td>{html.escape(r['share_note'] or '')}</td></tr>" for r in shared_jobs)
    on_rows = ''.join(f"<tr><td>{html.escape(r['username'])}</td><td>{html.escape(r['role'] or '')}</td><td>{html.escape(r['ip_address'] or '')}</td><td>{html.escape(r['login_time'] or '')}</td><td>{html.escape(r['last_seen'] or '')}</td></tr>" for r in online)
    online_html = f"<div class='card'><h2>Online Users</h2><table><tr><th>User</th><th>Role</th><th>IP</th><th>Login</th><th>Last Seen</th></tr>{on_rows}</table></div>" if has_permission_role(role, 'view_admin') else ""
    share_forms = ""
    if has_permission_role(role, "share_files"):
        share_forms += f"""<div class='card'><h2>Share a File</h2><form method='post'><input type='hidden' name='action' value='share_file'><div class='row3'><p><label>File</label><select name='file_index_id'>{file_opts}</select></p><p><label>Share with role</label><select name='shared_with_role'>{role_opts}</select></p><p><label>Note</label><input name='share_note'></p></div><button>Share File</button></form></div>"""
    if has_permission_role(role, "share_jobs"):
        share_forms += f"""<div class='card'><h2>Share a Job</h2><form method='post'><input type='hidden' name='action' value='share_job'><div class='row3'><p><label>Job</label><select name='job_id'>{job_opts}</select></p><p><label>Share with role</label><select name='shared_with_role'>{role_opts}</select></p><p><label>Note</label><input name='share_note'></p></div><button>Share Job</button></form></div>"""
    body = f"""
    <div class='grid'><div class='stat'>Your Role<b>{html.escape(role)}</b><span class='muted'>Permissions are role-based</span></div><div class='stat'>Active Sessions<b>{len(online)}</b><span class='muted'>Admins can revoke sessions</span></div><div class='stat'>Shared Files<b>{len(shared_files)}</b></div><div class='stat'>Shared Jobs<b>{len(shared_jobs)}</b></div></div>
    {share_forms}
    {online_html}
    <div class='card'><h2>Shared Files</h2><table><tr><th>File</th><th>Role Access</th><th>Shared By</th><th>Time</th><th>Note</th><th>Open</th></tr>{sf_rows}</table></div>
    <div class='card'><h2>Shared Jobs</h2><table><tr><th>Job</th><th>Role Access</th><th>Shared By</th><th>Time</th><th>Note</th></tr>{sj_rows}</table></div>
    <div class='card'><h2>Permission Classes</h2><p><b>Admin:</b> full control. <b>Manager:</b> edit jobs, money, files, workers. <b>Worker:</b> company worker read-only/assigned access. <b>Viewer:</b> company read-only. <b>Non-company:</b> outside user with only specifically shared items.</p></div>
    """
    return layout("Shared Sessions and Info Sharing", body, "sharing")
@app.route("/shared/file/<int:share_id>")
@login_required(any_permission=("view_shared_sessions", "view_customer_shared"))
def open_shared_file(share_id: int):
    from app.file_access_security import path_under_allowed_roots, get_allowed_file_roots, role_may_open_indexed_file

    row = db().execute("SELECT * FROM shared_files WHERE id=? AND active=1", (share_id,)).fetchone()
    if not row:
        abort(404)
    viewer_role = session.get("role") or "viewer"
    min_role = row["shared_with_role"] or "viewer"
    if not role_can_access_share(viewer_role, min_role):
        log_security_event(
            "shared_file_denied",
            session.get("username", ""),
            f"Share #{share_id} requires {min_role}, user is {viewer_role}",
            "WARN",
        )
        abort(403)
    allowed, reason = role_may_open_indexed_file(viewer_role, row["file_path"] or "")
    if not allowed and viewer_role not in ("admin", "manager"):
        log_security_event(
            "shared_sensitive_denied",
            session.get("username", ""),
            f"Blocked sensitive shared file: {reason}",
            "WARN",
        )
        abort(403)
    path = Path(row["file_path"])
    if not path.exists():
        flash("Shared file is no longer available at that path. Refresh sources.", "warning")
        return redirect(url_for("sharing_center"))
    roots = get_allowed_file_roots(BASE_DIR)
    if roots and not path_under_allowed_roots(path, roots):
        log_security_event(
            "shared_path_outside_roots",
            session.get("username", ""),
            f"Blocked shared path outside roots: {path}",
            "ERROR",
        )
        abort(403)
    return send_file(path, as_attachment=False)
@app.route("/files/upload", methods=["POST"])
@login_required("manage_files")
def upload_file():
    f = request.files.get("file")
    if not f or not f.filename:
        flash("No file selected.", "error"); return redirect(url_for("files"))
    dest = EVIDENCE_DIR / safe_name(f.filename)
    if dest.exists():
        dest = EVIDENCE_DIR / f"{dest.stem}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}{dest.suffix}"
    f.save(dest)
    scan_sources()
    log_event("File Upload", f"Uploaded {dest.name}")
    flash(f"Uploaded {dest.name} to evidence folder.", "success")
    return redirect(url_for("files"))
@app.route("/mobile")
@login_required("mobile_access")
def mobile_home():
    user = current_user(); role = user["role"] if user else "viewer"; perms = get_user_permissions(user["id"], role) if user else set()
    lan_ip = get_lan_ip(); port = int(os.environ.get("JRC_PORT", "8765"))
    if role == "non_company":
        shared_files = db().execute("SELECT COUNT(*) FROM shared_files WHERE active=1 AND shared_with_role='non_company'").fetchone()[0]
        shared_jobs = db().execute("SELECT COUNT(*) FROM shared_jobs WHERE active=1 AND shared_with_role='non_company'").fetchone()[0]
        body=f"""
        <div class='card'><h2>External Mobile Access</h2><p>This mobile screen is for outside/non-company access. It only shows items the owner/admin intentionally shares.</p><p><b>Phone URL on this network:</b> <code>http://{lan_ip}:{port}/mobile</code></p></div>
        <div class='grid'><div class='stat'>Account Type<b>{html.escape(role_display(role))}</b></div><div class='stat'>Shared Files<b>{shared_files}</b></div><div class='stat'>Shared Jobs<b>{shared_jobs}</b></div></div>
        <div class='card mobile-actions'><h2>Allowed Actions</h2><a class='btn' href='/sharing'>Open Shared Items</a> <a class='btn btn2' href='/logout'>Logout</a></div>
        """
        return layout("External Mobile Access", body, "mobile")
    if role == "customer":
        ensure_customer_request_schema()
        profile = ensure_customer_profile_for_current_user()
        open_reqs = db().execute("SELECT COUNT(*) FROM customer_job_requests WHERE customer_user_id=? AND status NOT IN ('Closed','Cancelled','Converted to Job')", (profile["id"],)).fetchone()[0]
        shared_files, shared_jobs = shared_counts_for_role(role)
        body = f"""
        <div class='card'><h2>Customer Mobile Portal</h2><p>Submit and track your job requests. Internal J&R job lists, payroll, and files are hidden.</p>
        <p><b>Phone URL on this network:</b> <code>http://{lan_ip}:{port}/mobile</code></p></div>
        <div class='grid'><div class='stat'>Open Requests<b>{open_reqs}</b></div><div class='stat'>Shared Files<b>{shared_files}</b></div><div class='stat'>Shared Jobs<b>{shared_jobs}</b></div></div>
        <div class='card mobile-actions'><h2>Allowed Actions</h2>
        <a class='btn' href='/customer/request'>Create Job Request</a>
        <a class='btn btn2' href='/customer/requests'>My Requests</a>
        <a class='btn btn2' href='/sharing'>Shared With Me</a>
        <a class='btn btn2' href='/chat'>Office Announcements</a>
        <a class='btn btn2' href='/logout'>Logout</a></div>
        """
        return layout("Customer Mobile Portal", body, "mobile")
    jobs_count = db().execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    active_jobs = db().execute("SELECT COUNT(*) FROM jobs WHERE status NOT LIKE 'Closed%'").fetchone()[0]
    files_count = db().execute("SELECT COUNT(*) FROM file_index").fetchone()[0] if "view_files" in perms else 0
    money_card = ""
    paid_col = ""
    if "view_money" in perms:
        gross = db().execute("SELECT COALESCE(SUM(paid),0) FROM jobs").fetchone()[0]
        money_card = f"<div class='stat'>Paid Income<b>{money(gross)}</b></div>"
        paid_col = "<th>Paid</th>"
    jobs_recent = db().execute("SELECT id,job_name,status,price,paid,updated_at FROM jobs ORDER BY updated_at DESC, id DESC LIMIT 8").fetchall() if "view_jobs" in perms else []
    jr = ''.join(f"<tr><td><a href='/mobile/job/{r['id']}'>{html.escape(r['job_name'])}</a></td><td>{html.escape(r['status'] or '')}</td>{('<td>'+money(r['paid'])+'</td>') if 'view_money' in perms else ''}</tr>" for r in jobs_recent)
    pipeline_snippet = ""
    if "view_jobs" in perms:
        try:
            from app.mobile_pipeline import pipeline_counts
            pc = pipeline_counts(db())
            pipeline_snippet = "<div class='card'><h2>Pipeline Snapshot</h2><div class='grid'>" + "".join(
                f"<div class='stat'><span class='muted'>{html.escape(k)}</span><b>{v}</b></div>" for k, v in pc.items() if v > 0
            ) + f"</div><p><a class='btn' href='/mobile/pipeline'>Open Job Pipeline Board</a></p></div>"
        except Exception:
            pipeline_snippet = "<div class='card'><p><a class='btn' href='/mobile/pipeline'>Open Job Pipeline Board</a></p></div>"
    body=f"""
    <div class='card'><h2>Mobile Access Center</h2><p>This is the phone-friendly home screen for J and R Construction Manager. Use it from a trusted LAN/VPN or secured cloud host.</p>
    <p><b>Phone URL on this network:</b> <code>http://{lan_ip}:{port}/mobile</code></p>
    <p class='muted'>This screen only shows actions your account is allowed to use.</p></div>
    <div class='grid'>{money_card}<div class='stat'>Active Jobs<b>{active_jobs}</b></div><div class='stat'>Total Jobs<b>{jobs_count}</b></div><div class='stat'>Indexed Files<b>{files_count if 'view_files' in perms else 'Limited'}</b></div></div>
    <div class='card mobile-actions'><h2>Quick Actions</h2>{('<a class=\'btn\' href=\'/mobile/pipeline\'>Job Pipeline Board</a>') if 'view_jobs' in perms else ''} {('<a class=\'btn\' href=\'/mobile/jobs\'>Mobile Jobs</a>') if 'view_jobs' in perms else ''} {('<a class=\'btn btn2\' href=\'/mobile/files\'>Mobile Files</a>') if 'view_files' in perms else ''} {('<a class=\'btn btn2\' href=\'/chat\'>Live Chat</a>') if ('view_shared_sessions' in perms or 'view_customer_shared' in perms) else ''} {('<a class=\'btn btn2\' href=\'/sharing\'>Shared Items</a>') if ('view_shared_sessions' in perms or 'view_customer_shared' in perms) else ''}</div>
    {pipeline_snippet}
    <div class='card'><h2>Recent Jobs</h2><table><tr><th>Job</th><th>Status</th>{paid_col}</tr>{jr}</table></div>
    <div class='card'><h2>Mobile Rules</h2><ul><li>Admins and managers can update records based on permissions.</li><li>Workers and viewers are read-only unless an owner/admin grants more access.</li><li>Non-company users only see intentionally shared items.</li></ul></div>
    """
    return layout("Mobile Access Center", body, "mobile")
@app.route("/mobile/jobs")
@login_required("mobile_access")
def mobile_jobs():
    user = current_user(); perms = get_user_permissions(user["id"], user["role"])
    if "view_jobs" not in perms:
        flash("This account can only use shared items, not the full job list.", "warning")
        return redirect(url_for("sharing_center"))
    rows = db().execute("SELECT id,job_name,status,price,paid,address,updated_at FROM jobs ORDER BY updated_at DESC, id DESC LIMIT 200").fetchall()
    if "view_money" in perms:
        trs = ''.join(f"<tr><td><a href='/mobile/job/{r['id']}'>{html.escape(r['job_name'] or '')}</a><br><span class='muted'>{html.escape(r['address'] or '')}</span></td><td>{html.escape(r['status'] or '')}</td><td>{money(r['price'])}</td><td>{money(r['paid'])}</td></tr>" for r in rows)
        heads = "<th>Job</th><th>Status</th><th>Price</th><th>Paid</th>"
    else:
        trs = ''.join(f"<tr><td><a href='/mobile/job/{r['id']}'>{html.escape(r['job_name'] or '')}</a><br><span class='muted'>{html.escape(r['address'] or '')}</span></td><td>{html.escape(r['status'] or '')}</td></tr>" for r in rows)
        heads = "<th>Job</th><th>Status</th>"
    full_jobs_link = "<a class='btn btn2' href='/jobs'>Full Jobs Page</a>" if 'view_jobs' in perms else ""
    body = f"""<div class='card mobile-actions'><a class='btn btn2' href='/mobile'>Back to Mobile Home</a> {full_jobs_link}</div><div class='card'><h2>Mobile Jobs</h2><table><tr>{heads}</tr>{trs}</table></div>"""
    return layout("Mobile Jobs", body, "mobile")

@app.route("/mobile/pipeline")
@login_required("mobile_access")
def mobile_pipeline():
    user = current_user()
    perms = get_user_permissions(user["id"], user["role"])
    if "view_jobs" not in perms:
        flash("This account can only use shared items, not the job pipeline.", "warning")
        return redirect(url_for("sharing_center"))
    from app.mobile_pipeline import render_mobile_pipeline_html
    body = (
        "<div class='card mobile-actions'><a class='btn btn2' href='/mobile'>Back to Mobile Home</a> "
        "<a class='btn btn2' href='/mobile/jobs'>List View</a></div>"
        + render_mobile_pipeline_html(db(), "view_money" in perms, money)
    )
    return layout("Job Pipeline", body, "mobile")

@app.route("/mobile/job/<int:job_id>")
@login_required("mobile_access")
def mobile_job_detail(job_id: int):
    user = current_user(); perms = get_user_permissions(user["id"], user["role"])
    if "view_jobs" not in perms:
        abort(403)
    job = db().execute("SELECT j.*, c.name AS customer_name, c.phone AS customer_phone, c.email AS customer_email FROM jobs j LEFT JOIN customers c ON c.id=j.customer_id WHERE j.id=?", (job_id,)).fetchone()
    if not job: abort(404)
    money_cards = ""
    money_sections = ""
    if "view_money" in perms:
        expenses = db().execute("SELECT category,vendor,description,amount,expense_date FROM expenses WHERE job_id=? ORDER BY id DESC LIMIT 50", (job_id,)).fetchall()
        pays = db().execute("SELECT w.name, wp.amount, wp.work_date, wp.notes FROM worker_payments wp LEFT JOIN workers w ON w.id=wp.worker_id WHERE wp.job_id=? ORDER BY wp.id DESC LIMIT 50", (job_id,)).fetchall()
        erows = ''.join(f"<tr><td>{html.escape(r['category'] or '')}</td><td>{html.escape(r['vendor'] or '')}</td><td>{html.escape(r['description'] or '')}</td><td>{money(r['amount'])}</td></tr>" for r in expenses)
        prows = ''.join(f"<tr><td>{html.escape(r['name'] or '')}</td><td>{money(r['amount'])}</td><td>{html.escape(r['work_date'] or '')}</td><td>{html.escape(r['notes'] or '')}</td></tr>" for r in pays)
        money_cards = f"<div class='stat'>Price<b>{money(job['price'])}</b></div><div class='stat'>Paid<b>{money(job['paid'])}</b></div><div class='stat'>Balance<b>{money(parse_float(job['price'])-parse_float(job['paid']))}</b></div>"
        money_sections = f"<div class='card'><h2>Expenses</h2><table><tr><th>Category</th><th>Vendor</th><th>Description</th><th>Amount</th></tr>{erows}</table></div><div class='card'><h2>Worker Payments</h2><table><tr><th>Worker</th><th>Amount</th><th>Date</th><th>Notes</th></tr>{prows}</table></div>"
    full_jobs_link = "<a class='btn btn2' href='/jobs'>Full Jobs Page</a>" if 'view_jobs' in perms else ""
    body = f"""
    <div class='card mobile-actions'><a class='btn btn2' href='/mobile/jobs'>Back to Mobile Jobs</a> {full_jobs_link}</div>
    <div class='grid'><div class='stat'>Status<b>{html.escape(job['status'] or '')}</b></div>{money_cards}</div>
    <div class='card'><h2>{html.escape(job['job_name'] or '')}</h2><p><b>Customer:</b> {html.escape(job['customer_name'] or '')} &nbsp; <b>Phone:</b> {html.escape(job['customer_phone'] or '')}</p><p><b>Address:</b> {html.escape(job['address'] or '')}</p><p><b>Scope:</b><br>{html.escape(job['scope'] or '')}</p><p><b>Notes:</b><br>{html.escape(job['notes'] or '')}</p></div>
    {money_sections}
    """
    return layout("Mobile Job Detail", body, "mobile")
@app.route("/mobile/files")
@login_required("mobile_access")
def mobile_files():
    user = current_user(); perms = get_user_permissions(user["id"], user["role"])
    if "view_files" not in perms:
        flash("This account can only open files specifically shared by the owner/admin.", "warning")
        return redirect(url_for("sharing_center"))
    q = request.args.get('q','').strip()
    if q:
        like=f"%{q}%"
        rows = db().execute("SELECT fi.*, fs.label FROM file_index fi LEFT JOIN file_sources fs ON fs.id=fi.source_id WHERE fi.file_name LIKE ? OR fi.analysis LIKE ? OR fs.label LIKE ? ORDER BY fi.modified_at DESC LIMIT 150", (like,like,like)).fetchall()
    else:
        rows = db().execute("SELECT fi.*, fs.label FROM file_index fi LEFT JOIN file_sources fs ON fs.id=fi.source_id ORDER BY fi.modified_at DESC LIMIT 150").fetchall()
    trs = ''.join(f"<tr><td>{html.escape(r['file_name'] or '')}<br><span class='muted'>{html.escape(r['analysis'] or '')}</span></td><td>{html.escape(r['label'] or '')}</td><td><a href='/files/open/{r['id']}'>Open</a></td></tr>" for r in rows)
    upload = ""
    if has_permission_role(session.get('role'), 'manage_files'):
        upload = """<div class='card'><h2>Upload Evidence / Receipt</h2><form method='post' action='/files/upload' enctype='multipart/form-data'><input type='file' name='file'><button>Upload to Evidence</button></form></div>"""
    body = f"""
    <div class='card mobile-actions'><a class='btn btn2' href='/mobile'>Back to Mobile Home</a> <a class='btn btn2' href='/files/refresh'>Refresh Sources</a></div>
    {upload}
    <div class='card'><h2>Mobile File Search</h2><form method='get'><input name='q' value='{html.escape(q)}' placeholder='Search receipts, invoices, tax files, jobs'><button>Search</button></form></div>
    <div class='card'><h2>Files</h2><table><tr><th>File</th><th>Source</th><th>Open</th></tr>{trs}</table></div>
    """
    return layout("Mobile Files", body, "mobile")
@app.route("/static/manifest.json")
def pwa_manifest():
    return jsonify({
        "name": "J and R Construction Manager",
        "short_name": "J&R Manager",
        "start_url": "/mobile",
        "scope": "/",
        "display": "standalone",
        "background_color": "#000000",
        "theme_color": "#84cc16",
        "description": "Mobile access for J and R Construction Manager jobs, files, and shared sessions.",
        "icons": []
    })
@app.route("/static/service-worker.js")
def service_worker():
    js = """self.addEventListener('install',event=>self.skipWaiting());\nself.addEventListener('activate',event=>self.clients.claim());\nself.addEventListener('fetch',event=>{});\n"""
    return Response(js, mimetype='application/javascript')
@app.route("/ai", methods=["GET", "POST"])
@login_required("configure_ai")
def ai_sources():
    if request.method == "POST":
        db().execute("INSERT INTO ai_sources (label,source_type,folder_path,api_enabled,status,notes,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                     (request.form.get("label"), request.form.get("source_type"), request.form.get("folder_path"), 1 if request.form.get("api_enabled") == "on" else 0, request.form.get("status") or "Configured", request.form.get("notes"), now_iso(), now_iso()))
        db().commit(); flash("AI/ChatGPT source saved.", "success"); return redirect(url_for("ai_sources"))
    rows = db().execute("SELECT * FROM ai_sources ORDER BY id DESC").fetchall()
    trs = ''.join(f"<tr><td>{html.escape(r['label'] or '')}</td><td>{html.escape(r['source_type'] or '')}</td><td>{html.escape(r['folder_path'] or '')}</td><td>{'Yes' if r['api_enabled'] else 'No'}</td><td>{html.escape(r['status'] or '')}</td><td>{html.escape(r['notes'] or '')}</td></tr>" for r in rows)
    body = f"""
    <div class='card'><h2>ChatGPT / AI Source Rules</h2><p><b>Safe rule:</b> This app can scan ChatGPT export/import files and can later use an API key you intentionally configure. It cannot directly read private ChatGPT Business conversations or workspace files by itself.</p></div>
    <div class='card'><h2>Add Source</h2><form method='post'><div class='row3'><p><label>Label</label><input name='label' value='ChatGPT Business Export'></p><p><label>Type</label><select name='source_type'><option>chatgpt-import-folder</option><option>openai-api-planned</option><option>manual-export</option></select></p><p><label>Folder / Endpoint Note</label><input name='folder_path' value='{html.escape(str(CHATGPT_IMPORTS_DIR))}'></p></div><p><label>Notes</label><textarea name='notes'></textarea></p><p><label><input type='checkbox' name='api_enabled'> API enabled later after owner config</label></p><button>Save Source</button></form></div>
    <div class='card'><h2>Configured Sources</h2><table><tr><th>Label</th><th>Type</th><th>Folder/Endpoint</th><th>API</th><th>Status</th><th>Notes</th></tr>{trs}</table></div>
    """
    return layout("ChatGPT / AI Sources", body, "ai")
@app.route("/api/mobile/dashboard")
@login_required("mobile_access")
def api_mobile_dashboard():
    user = current_user()
    role = normalize_role_for_session(user["role"] if user else "viewer")
    if is_customer_or_external(role):
        shared_files, shared_jobs = shared_counts_for_role(role)
        return jsonify({"role": role, "shared_files": shared_files, "shared_jobs": shared_jobs, "internal_metrics_hidden": True})
    snap = data_status_snapshot()
    perms = get_user_permissions(user["id"], role)
    if "view_money" not in perms:
        snap.pop("expenses", None)
        snap.pop("worker_payments", None)
        snap.pop("invoices", None)
    return jsonify(snap)
@app.route("/api/mobile/jobs")
@login_required("mobile_access")
def api_mobile_jobs():
    user = current_user()
    role = normalize_role_for_session(user["role"] if user else "viewer")
    perms = get_user_permissions(user["id"], role)
    if is_customer_or_external(role) or "view_jobs" not in perms:
        return jsonify([])
    rows = db().execute("SELECT id, job_name, status, price, paid, updated_at FROM jobs ORDER BY updated_at DESC, id DESC LIMIT 100").fetchall()
    out = []
    for r in rows:
        item = {"id": r["id"], "job_name": r["job_name"], "status": r["status"], "updated_at": r["updated_at"]}
        if "view_money" in perms:
            item["price"] = r["price"]
            item["paid"] = r["paid"]
        out.append(item)
    return jsonify(out)
@app.route("/api/mobile/pipeline")
@login_required("mobile_access")
def api_mobile_pipeline():
    user = current_user()
    role = normalize_role_for_session(user["role"] if user else "viewer")
    perms = get_user_permissions(user["id"], role)
    if is_customer_or_external(role) or "view_jobs" not in perms:
        return jsonify({"error": "forbidden", "internal_metrics_hidden": True}), 403
    from app.mobile_pipeline import pipeline_api_payload
    return jsonify(pipeline_api_payload(db()))

@app.route("/api/mobile/files")
@login_required("mobile_access")
def api_mobile_files():
    user = current_user()
    role = normalize_role_for_session(user["role"] if user else "viewer")
    perms = get_user_permissions(user["id"], role)
    if is_customer_or_external(role) or "view_files" not in perms:
        return jsonify([])
    rows = db().execute("SELECT id,file_name,extension,size,modified_at,analysis FROM file_index ORDER BY modified_at DESC LIMIT 100").fetchall()
    return jsonify([dict(r) for r in rows])
@app.route("/api/data_status")
@login_required("audit")
def api_data_status():
    return jsonify(data_status_snapshot())
def ensure_bookkeeping_schema() -> None:
    """Auto-repair bookkeeping/filekeeping tables and columns."""
    with direct_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS bookkeeping_ledgers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, entry_date TEXT, entry_type TEXT, category TEXT,
            job_id INTEGER, source_table TEXT, source_id INTEGER, description TEXT,
            debit REAL DEFAULT 0, credit REAL DEFAULT 0, status TEXT DEFAULT 'Open',
            receipt_status TEXT, created_at TEXT, updated_at TEXT, notes TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS bookkeeping_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT, rule_name TEXT, match_text TEXT, category TEXT,
            entry_type TEXT, active INTEGER DEFAULT 1, notes TEXT, created_at TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS bookkeeping_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_time TEXT, run_type TEXT, total_income REAL DEFAULT 0,
            total_expenses REAL DEFAULT 0, total_worker_pay REAL DEFAULT 0, total_receivables REAL DEFAULT 0,
            unmatched_receipts INTEGER DEFAULT 0, missing_receipts INTEGER DEFAULT 0, duplicate_file_names INTEGER DEFAULT 0,
            open_jobs INTEGER DEFAULT 0, notes TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS filekeeping_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_time TEXT, source_count INTEGER DEFAULT 0,
            indexed_files INTEGER DEFAULT 0, duplicate_file_names INTEGER DEFAULT 0, receipt_like_files INTEGER DEFAULT 0,
            missing_receipts INTEGER DEFAULT 0, inactive_sources INTEGER DEFAULT 0,
            missing_source_paths INTEGER DEFAULT 0, notes TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS bookkeeping_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, alert_type TEXT, severity TEXT, title TEXT,
            message TEXT, related_table TEXT, related_id INTEGER, resolved INTEGER DEFAULT 0,
            resolved_at TEXT, resolved_by TEXT)""")
        # Seed practical J&R categories/rules once.
        existing = conn.execute("SELECT COUNT(*) FROM bookkeeping_rules").fetchone()[0]
        if existing == 0:
            seeds = [
                ("Lowe's / materials", "lowe,lowes,home depot,carolina brick", "Materials & Supplies", "Expense"),
                ("Worker/helper pay", "brandon,jackie,helper,payroll,worker", "Worker/Helper Pay", "Expense"),
                ("Insurance/admin", "insurance,w9,ein,mcclure,certificate", "Insurance/Admin", "Expense"),
                ("Vehicle/truck", "fuel,gas,truck,silverado,trailer", "Vehicle/Truck", "Expense"),
                ("Tools/equipment", "tool,rental,drill,saw,blade", "Tools/Equipment", "Expense"),
                ("Invoices/payments", "invoice,paid,deposit,balance,check,cash,cash app", "Income/Receivable", "Income"),
                ("Owner draw / paid myself", "owner draw,paid myself,business checking,office full day", "Owner Draw", "Owner Draw"),
            ]
            for rule_name, match_text, category, entry_type in seeds:
                conn.execute("INSERT INTO bookkeeping_rules(rule_name, match_text, category, entry_type, active, created_at) VALUES (?,?,?,?,1,?)", (rule_name, match_text, category, entry_type, now_iso()))
        conn.commit()
def bookkeeping_snapshot(conn: sqlite3.Connection) -> dict:
    ensure_bookkeeping_schema()
    income = conn.execute("SELECT COALESCE(SUM(paid),0) FROM jobs").fetchone()[0] or 0
    receivables = conn.execute("SELECT COALESCE(SUM(CASE WHEN price>paid THEN price-paid ELSE 0 END),0) FROM jobs").fetchone()[0] or 0
    expenses = conn.execute("SELECT COALESCE(SUM(amount),0) FROM expenses").fetchone()[0] or 0
    worker_pay = conn.execute("SELECT COALESCE(SUM(amount),0) FROM worker_payments WHERE status IN ('Paid','Approved','Pending')").fetchone()[0] or 0
    worker_fees = conn.execute("SELECT COALESCE(SUM(COALESCE(cost_fee,0)),0) FROM worker_payments WHERE status IN ('Paid','Approved','Pending')").fetchone()[0] or 0
    missing_receipts = conn.execute("SELECT COUNT(*) FROM expenses WHERE COALESCE(receipt_status,'') NOT IN ('Receipt saved','Confirmed','No receipt')").fetchone()[0] or 0
    open_jobs = conn.execute("SELECT COUNT(*) FROM jobs WHERE COALESCE(status,'') NOT IN ('Closed','Completed','Paid/Closed')").fetchone()[0] or 0
    duplicate_names = 0
    try:
        duplicate_names = conn.execute("SELECT COUNT(*) FROM (SELECT file_name FROM file_index GROUP BY file_name HAVING COUNT(*)>1)").fetchone()[0] or 0
    except Exception:
        pass
    receipt_files = 0
    try:
        receipt_files = conn.execute("SELECT COUNT(*) FROM file_index WHERE lower(file_name) LIKE '%receipt%' OR lower(file_name) LIKE '%lowe%' OR lower(file_name) LIKE '%billing%' OR lower(file_name) LIKE '%ticket%'").fetchone()[0] or 0
    except Exception:
        pass
    return {
        'income': float(income), 'receivables': float(receivables), 'expenses': float(expenses),
        'worker_pay': float(worker_pay), 'worker_fees': float(worker_fees), 'total_cost': float(expenses)+float(worker_pay)+float(worker_fees),
        'profit_cash_basis': float(income)-float(expenses)-float(worker_pay)-float(worker_fees),
        'missing_receipts': int(missing_receipts), 'open_jobs': int(open_jobs), 'duplicate_file_names': int(duplicate_names),
        'receipt_files': int(receipt_files)
    }
def reconcile_bookkeeping(conn: sqlite3.Connection, username: str = 'system') -> dict:
    """Build/update ledger rows from jobs, expenses, and worker payments without deleting source records."""
    ensure_bookkeeping_schema()
    now = now_iso()
    created = 0
    # Income from paid job amounts.
    for r in conn.execute("SELECT id, job_name, paid, payment_method, updated_at FROM jobs WHERE COALESCE(paid,0)>0").fetchall():
        exists = conn.execute("SELECT id FROM bookkeeping_ledgers WHERE source_table='jobs' AND source_id=? AND entry_type='Income'", (r['id'],)).fetchone()
        if not exists:
            conn.execute("INSERT INTO bookkeeping_ledgers(entry_date,entry_type,category,job_id,source_table,source_id,description,debit,credit,status,created_at,updated_at,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         ((r['updated_at'] or now)[:10], 'Income', 'Job Income', r['id'], 'jobs', r['id'], f"Payment recorded for {r['job_name']}", 0, float(r['paid'] or 0), 'Reconciled', now, now, f"Created by {username}")); created += 1
    for r in conn.execute("SELECT * FROM expenses WHERE COALESCE(amount,0)>0").fetchall():
        exists = conn.execute("SELECT id FROM bookkeeping_ledgers WHERE source_table='expenses' AND source_id=?", (r['id'],)).fetchone()
        if not exists:
            conn.execute("INSERT INTO bookkeeping_ledgers(entry_date,entry_type,category,job_id,source_table,source_id,description,debit,credit,status,receipt_status,created_at,updated_at,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         ((r['expense_date'] or now)[:10], 'Expense', r['category'] or 'Expense', r['job_id'], 'expenses', r['id'], r['description'] or r['vendor'] or 'Expense', float(r['amount'] or 0), 0, 'Reconciled', r['receipt_status'], now, now, f"Vendor: {r['vendor'] or ''}")); created += 1
    for r in conn.execute("SELECT wp.*, w.name worker_name FROM worker_payments wp LEFT JOIN workers w ON w.id=wp.worker_id WHERE COALESCE(wp.amount,0)>0").fetchall():
        exists = conn.execute("SELECT id FROM bookkeeping_ledgers WHERE source_table='worker_payments' AND source_id=?", (r['id'],)).fetchone()
        if not exists:
            desc = f"Worker pay: {r['worker_name'] or 'worker'} - {r['description'] or ''}"
            conn.execute("INSERT INTO bookkeeping_ledgers(entry_date,entry_type,category,job_id,source_table,source_id,description,debit,credit,status,created_at,updated_at,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         ((r['work_date'] or now)[:10], 'Expense', 'Worker/Helper Pay', r['job_id'], 'worker_payments', r['id'], desc, float(r['amount'] or 0), 0, r['status'] or 'Open', now, now, f"Cost fee separate: {money(r['cost_fee'] or 0)}")); created += 1
    if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='owner_draws'").fetchone():
        for r in conn.execute("SELECT * FROM owner_draws WHERE COALESCE(amount,0)>0").fetchall():
            exists = conn.execute("SELECT id FROM bookkeeping_ledgers WHERE source_table='owner_draws' AND source_id=?", (r['id'],)).fetchone()
            if not exists:
                desc = f"Owner draw: {r['description'] or r['work_type'] or 'Paid myself'}"
                conn.execute("INSERT INTO bookkeeping_ledgers(entry_date,entry_type,category,job_id,source_table,source_id,description,debit,credit,status,created_at,updated_at,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             ((r['draw_date'] or now)[:10], 'Owner Draw', 'Owner Draw / Equity', r['job_id'], 'owner_draws', r['id'], desc, float(r['amount'] or 0), 0, 'Reconciled', now, now, f"Paid from: {r['paid_from_account'] or ''}; not a Schedule C expense")); created += 1
    snap = bookkeeping_snapshot(conn)
    conn.execute("INSERT INTO bookkeeping_runs(run_time,run_type,total_income,total_expenses,total_worker_pay,total_receivables,unmatched_receipts,missing_receipts,duplicate_file_names,open_jobs,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                 (now, 'Manual Reconciliation', snap['income'], snap['expenses'], snap['worker_pay'], snap['receivables'], snap['receipt_files'], snap['missing_receipts'], snap['duplicate_file_names'], snap['open_jobs'], f"Created {created} ledger row(s). Run by {username}."))
    conn.commit()
    snap['created_ledgers'] = created
    return snap
def ensure_payroll_schema() -> None:
    """Auto-repair payroll/accounting columns for older databases."""
    with direct_db() as conn:
        def columns(table: str) -> set[str]:
            return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        conn.execute("""CREATE TABLE IF NOT EXISTS payroll_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT, period_name TEXT, start_date TEXT, end_date TEXT,
            status TEXT DEFAULT 'Open', total_worker_pay REAL DEFAULT 0, total_cost_fees REAL DEFAULT 0,
            total_hours REAL DEFAULT 0, created_at TEXT, closed_at TEXT, notes TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS job_cost_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER, snapshot_time TEXT, revenue REAL DEFAULT 0,
            deposits REAL DEFAULT 0, paid REAL DEFAULT 0, material_expenses REAL DEFAULT 0, worker_pay REAL DEFAULT 0,
            payroll_cost_fees REAL DEFAULT 0, owner_labor_value REAL DEFAULT 0, total_known_cost REAL DEFAULT 0,
            estimated_profit REAL DEFAULT 0, notes TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER, invoice_number TEXT, invoice_type TEXT DEFAULT 'Invoice',
            issue_date TEXT, due_date TEXT, status TEXT DEFAULT 'Draft', subtotal REAL DEFAULT 0,
            deposit_due REAL DEFAULT 0, paid_amount REAL DEFAULT 0, balance_due REAL DEFAULT 0,
            payment_terms TEXT, notes TEXT, created_at TEXT, updated_at TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS invoice_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER, job_id INTEGER, payment_date TEXT,
            amount REAL DEFAULT 0, method TEXT, reference TEXT, notes TEXT, created_at TEXT)""")
        worker_payment_adds = {
            "hours": "REAL DEFAULT 0",
            "rate": "REAL DEFAULT 0",
            "cost_fee": "REAL DEFAULT 0",
            "approved_by": "TEXT",
            "approved_at": "TEXT",
            "paid_at": "TEXT",
            "payroll_period_id": "INTEGER",
            "source": "TEXT DEFAULT 'manual'"
        }
        existing = columns("worker_payments")
        for col, definition in worker_payment_adds.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE worker_payments ADD COLUMN {col} {definition}")
        conn.commit()
def ensure_job_application_schema() -> None:
    """Auto-repair job application, worker onboarding, and insurance information tables."""
    with direct_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS job_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            updated_at TEXT,
            status TEXT DEFAULT 'Pending Owner Review',
            requested_username TEXT,
            desired_role TEXT DEFAULT 'worker',
            full_name TEXT,
            email TEXT,
            recovery_email TEXT,
            phone TEXT,
            address TEXT,
            date_of_birth TEXT,
            emergency_contact_name TEXT,
            emergency_contact_phone TEXT,
            preferred_rate REAL DEFAULT 0,
            rate_type TEXT DEFAULT 'daily',
            availability TEXT,
            transportation TEXT,
            drivers_license_status TEXT,
            own_tools TEXT,
            skills TEXT,
            experience_years REAL DEFAULT 0,
            work_history TEXT,
            references_text TEXT,
            insurance_full_legal_name TEXT,
            insurance_address TEXT,
            insurance_phone TEXT,
            insurance_email TEXT,
            insurance_date_of_birth TEXT,
            insurance_driver_license_state TEXT,
            insurance_driver_license_number TEXT,
            insurance_vehicle_use TEXT,
            insurance_employment_classification TEXT,
            insurance_requested_coverage TEXT,
            insurance_notes TEXT,
            w9_status TEXT DEFAULT 'Needed if paid as contractor',
            id_document_status TEXT DEFAULT 'Not received',
            owner_notes TEXT,
            reviewed_by TEXT,
            reviewed_at TEXT,
            request_ip TEXT,
            request_user_agent TEXT,
            account_request_id INTEGER,
            approved_user_id INTEGER
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS application_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time TEXT,
            application_id INTEGER,
            event_type TEXT,
            username TEXT,
            ip_address TEXT,
            message TEXT
        )""")
        for stmt in [
            "ALTER TABLE job_applications ADD COLUMN account_request_id INTEGER",
            "ALTER TABLE job_applications ADD COLUMN approved_user_id INTEGER",
            "ALTER TABLE job_applications ADD COLUMN insurance_requested_coverage TEXT",
            "ALTER TABLE job_applications ADD COLUMN id_document_status TEXT DEFAULT 'Not received'",
            "ALTER TABLE job_applications ADD COLUMN w9_status TEXT DEFAULT 'Needed if paid as contractor'",
        ]:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
        conn.commit()
    from app.application_notifications import ensure_notification_columns

    with direct_db() as conn:
        ensure_notification_columns(conn)


def log_application_event(application_id: int, event_type: str, message: str, username: str = "") -> None:
    try:
        with direct_db() as conn:
            conn.execute("INSERT INTO application_events(event_time,application_id,event_type,username,ip_address,message) VALUES(?,?,?,?,?,?)",
                         (now_iso(), application_id, event_type, username or session.get('username',''), client_ip(), message))
            conn.commit()
    except Exception:
        pass


def job_cost_row(conn: sqlite3.Connection, job_id: int) -> dict[str, float]:
    job = conn.execute("SELECT COALESCE(price,0) price, COALESCE(deposit,0) deposit, COALESCE(paid,0) paid FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return {"revenue":0,"deposit":0,"paid":0,"expenses":0,"worker_pay":0,"cost_fees":0,"owner_labor":0,"total_cost":0,"profit":0,"balance":0}
    exp = conn.execute("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE job_id=?", (job_id,)).fetchone()[0] or 0
    wp = conn.execute("SELECT COALESCE(SUM(amount),0) FROM worker_payments WHERE job_id=? AND status IN ('Paid','Approved','Pending')", (job_id,)).fetchone()[0] or 0
    cf = conn.execute("SELECT COALESCE(SUM(COALESCE(cost_fee,0)),0) FROM worker_payments WHERE job_id=? AND status IN ('Paid','Approved','Pending')", (job_id,)).fetchone()[0] or 0
    ol = conn.execute("SELECT COALESCE(SUM(hours*rate),0) FROM owner_labor WHERE job_id=?", (job_id,)).fetchone()[0] or 0
    revenue = float(job["price"] or 0)
    paid = float(job["paid"] or 0)
    deposit = float(job["deposit"] or 0)
    total_cost = float(exp or 0) + float(wp or 0) + float(cf or 0)
    profit = revenue - total_cost
    return {"revenue":revenue,"deposit":deposit,"paid":paid,"expenses":float(exp or 0),"worker_pay":float(wp or 0),"cost_fees":float(cf or 0),"owner_labor":float(ol or 0),"total_cost":total_cost,"profit":profit,"balance":max(revenue-paid,0)}
@app.before_request
def payroll_auto_repair_before_request():
    # Safe no-op if already repaired. Keeps older installs from breaking payroll pages.
    if request.endpoint not in {"static", "service_worker"}:
        try:
            ensure_payroll_schema()
            ensure_bookkeeping_schema()
            ensure_job_application_schema()
        except Exception:
            pass
def filekeeping_snapshot(conn: sqlite3.Connection) -> dict:
    ensure_bookkeeping_schema()
    try:
        source_count = conn.execute("SELECT COUNT(*) FROM file_sources WHERE active=1").fetchone()[0] or 0
        inactive_sources = conn.execute("SELECT COUNT(*) FROM file_sources WHERE active=0").fetchone()[0] or 0
        indexed_files = conn.execute("SELECT COUNT(*) FROM file_index").fetchone()[0] or 0
        receipt_like = conn.execute("SELECT COUNT(*) FROM file_index WHERE lower(file_name) LIKE '%receipt%' OR lower(file_name) LIKE '%lowe%' OR lower(file_name) LIKE '%billing%' OR lower(file_name) LIKE '%ticket%' OR lower(file_name) LIKE '%invoice%' OR lower(file_name) LIKE '%paid%'").fetchone()[0] or 0
        duplicates = conn.execute("SELECT COUNT(*) FROM (SELECT lower(file_name) n FROM file_index GROUP BY lower(file_name) HAVING COUNT(*)>1)").fetchone()[0] or 0
    except Exception:
        source_count = inactive_sources = indexed_files = receipt_like = duplicates = 0
    missing_paths = 0
    try:
        for r in conn.execute("SELECT folder_path FROM file_sources WHERE active=1").fetchall():
            if not Path(r['folder_path']).exists():
                missing_paths += 1
    except Exception:
        pass
    try:
        missing_receipts = conn.execute("SELECT COUNT(*) FROM expenses WHERE COALESCE(receipt_status,'') NOT IN ('Receipt saved','Confirmed','No receipt')").fetchone()[0] or 0
    except Exception:
        missing_receipts = 0
    return {'source_count': source_count, 'inactive_sources': inactive_sources, 'indexed_files': indexed_files,
            'receipt_like_files': receipt_like, 'duplicate_file_names': duplicates,
            'missing_source_paths': missing_paths, 'missing_receipts': missing_receipts}
def run_filekeeping_review(conn: sqlite3.Connection, username: str = 'system') -> dict:
    snap = filekeeping_snapshot(conn)
    now = now_iso()
    notes = []
    if snap['missing_source_paths']:
        notes.append(f"{snap['missing_source_paths']} active source path(s) missing on this PC")
    if snap['duplicate_file_names']:
        notes.append(f"{snap['duplicate_file_names']} duplicate filename group(s) found")
    if snap['missing_receipts']:
        notes.append(f"{snap['missing_receipts']} expense record(s) need receipt review")
    if not notes:
        notes.append("Filekeeping review clean")
    conn.execute("INSERT INTO filekeeping_reviews(run_time,source_count,indexed_files,duplicate_file_names,receipt_like_files,missing_receipts,inactive_sources,missing_source_paths,notes) VALUES(?,?,?,?,?,?,?,?,?)",
                 (now, snap['source_count'], snap['indexed_files'], snap['duplicate_file_names'], snap['receipt_like_files'], snap['missing_receipts'], snap['inactive_sources'], snap['missing_source_paths'], '; '.join(notes)))
    # Create visible alerts, but avoid repeating unresolved identical titles too aggressively.
    def alert(kind, severity, title, message):
        existing = conn.execute("SELECT id FROM bookkeeping_alerts WHERE resolved=0 AND title=? AND alert_type=?", (title, kind)).fetchone()
        if not existing:
            conn.execute("INSERT INTO bookkeeping_alerts(created_at,alert_type,severity,title,message) VALUES(?,?,?,?,?)", (now, kind, severity, title, message))
    if snap['missing_source_paths']:
        alert('file_source', 'Warning', 'Missing file source path', 'One or more active file sources do not exist on this PC. Check Dropbox sync paths and source settings.')
    if snap['duplicate_file_names']:
        alert('duplicate_files', 'Info', 'Duplicate file names detected', 'Duplicate names may be normal, but review before relying on one copy as the final evidence file.')
    if snap['missing_receipts']:
        alert('receipts', 'Warning', 'Expenses need receipt review', 'Some expense records are missing confirmed receipt status.')
    conn.commit()
    snap['notes'] = '; '.join(notes)
    return snap
@app.route("/filekeeping", methods=["GET", "POST"])
@login_required("view_filekeeping")
def filekeeping():
    conn = db(); ensure_bookkeeping_schema()
    user = current_user(); perms = get_user_permissions(user['id'], user['role'])
    if request.method == 'POST':
        if 'manage_filekeeping' not in perms:
            abort(403)
        action = request.form.get('action')
        if action == 'review':
            refresh_file_index(conn)
            snap = run_filekeeping_review(conn, user['username'])
            log_event('Filekeeping', f"Filekeeping review run: {snap.get('notes','')}")
            flash('Filekeeping review completed and source index refreshed.', 'success')
        elif action == 'resolve_alert':
            aid = int(request.form.get('alert_id') or 0)
            conn.execute("UPDATE bookkeeping_alerts SET resolved=1, resolved_at=?, resolved_by=? WHERE id=?", (now_iso(), user['username'], aid))
            conn.commit(); flash('Alert marked resolved.', 'success')
        return redirect(url_for('filekeeping'))
    snap = filekeeping_snapshot(conn)
    alerts = conn.execute("SELECT * FROM bookkeeping_alerts WHERE resolved=0 ORDER BY created_at DESC LIMIT 50").fetchall()
    reviews = conn.execute("SELECT * FROM filekeeping_reviews ORDER BY run_time DESC LIMIT 10").fetchall()
    sources = conn.execute("SELECT * FROM file_sources ORDER BY active DESC, label").fetchall()
    duplicate_rows=[]
    try:
        duplicate_rows = conn.execute("SELECT lower(file_name) name, COUNT(*) c FROM file_index GROUP BY lower(file_name) HAVING COUNT(*)>1 ORDER BY c DESC LIMIT 25").fetchall()
    except Exception:
        pass
    alerts_html = ''.join(f"<tr><td><span class='badge'>{html.escape(a['severity'] or '')}</span></td><td>{html.escape(a['title'] or '')}<br><span class='muted'>{html.escape(a['message'] or '')}</span></td><td>{html.escape(a['created_at'] or '')}</td><td><form method='post'><input type='hidden' name='action' value='resolve_alert'><input type='hidden' name='alert_id' value='{a['id']}'><button>Resolve</button></form></td></tr>" for a in alerts) or "<tr><td colspan='4'>No open alerts.</td></tr>"
    reviews_html = ''.join(f"<tr><td>{html.escape(r['run_time'] or '')}</td><td>{r['source_count']}</td><td>{r['indexed_files']}</td><td>{r['receipt_like_files']}</td><td>{r['missing_receipts']}</td><td>{r['duplicate_file_names']}</td><td>{html.escape(r['notes'] or '')}</td></tr>" for r in reviews) or "<tr><td colspan='7'>No reviews yet.</td></tr>"
    source_html = ''.join(f"<tr><td>{html.escape(src['label'] or '')}</td><td>{html.escape(src['source_type'] or '')}</td><td>{html.escape(src['folder_path'] or '')}</td><td>{'Active' if src['active'] else 'Inactive'}</td><td>{'OK' if Path(src['folder_path'] or '').exists() else 'Missing on this PC'}</td></tr>" for src in sources)
    dup_html = ''.join(f"<tr><td>{html.escape(r['name'] or '')}</td><td>{r['c']}</td></tr>" for r in duplicate_rows) or "<tr><td colspan='2'>No duplicate filename groups found.</td></tr>"
    body=f"""
    <div class='grid'>
      <div class='stat'>Active Sources<b>{snap['source_count']}</b></div>
      <div class='stat'>Indexed Files<b>{snap['indexed_files']}</b></div>
      <div class='stat'>Receipt/Evidence-Like Files<b>{snap['receipt_like_files']}</b></div>
      <div class='stat'>Missing Source Paths<b>{snap['missing_source_paths']}</b></div>
      <div class='stat'>Duplicate Names<b>{snap['duplicate_file_names']}</b></div>
      <div class='stat'>Expense Receipts To Review<b>{snap['missing_receipts']}</b></div>
    </div>
    <div class='card'><h2>Filekeeping Control Center</h2><p class='muted'>Refreshes Dropbox/local/ChatGPT-import sources, checks receipts and duplicate names, and creates visible alerts for admin review.</p><form method='post'><input type='hidden' name='action' value='review'><button>Run Filekeeping Review + Refresh</button> <a class='btn btn2' href='/files'>Open File Explorer</a> <a class='btn btn2' href='/bookkeeping'>Open Bookkeeping</a></form></div>
    <div class='card'><h2>Open Alerts</h2><table><tr><th>Level</th><th>Alert</th><th>Created</th><th>Action</th></tr>{alerts_html}</table></div>
    <div class='card'><h2>Recent Filekeeping Reviews</h2><table><tr><th>Run</th><th>Sources</th><th>Files</th><th>Receipt Files</th><th>Missing Receipts</th><th>Duplicates</th><th>Notes</th></tr>{reviews_html}</table></div>
    <div class='card'><h2>Source Health</h2><table><tr><th>Label</th><th>Type</th><th>Folder</th><th>Status</th><th>PC Check</th></tr>{source_html}</table></div>
    <div class='card'><h2>Duplicate Filename Groups</h2><table><tr><th>File Name</th><th>Count</th></tr>{dup_html}</table></div>
    """
    return layout('Filekeeping', body, 'filekeeping')
@app.route("/bookkeeping", methods=["GET", "POST"])
@login_required("view_bookkeeping")
def bookkeeping():
    conn = db(); ensure_bookkeeping_schema(); ensure_payroll_schema()
    user = current_user(); perms = get_user_permissions(user["id"], user["role"])
    if request.method == "POST":
        if "manage_bookkeeping" not in perms:
            abort(403)
        action = request.form.get("action")
        if action == "reconcile":
            snap = reconcile_bookkeeping(conn, user["username"])
            log_event("Bookkeeping", f"Reconciled bookkeeping; created {snap.get('created_ledgers',0)} ledger rows")
            flash(f"Bookkeeping reconciled. {snap.get('created_ledgers',0)} new ledger row(s) created.", "success")
        elif action == "add_rule":
            conn.execute("INSERT INTO bookkeeping_rules(rule_name,match_text,category,entry_type,active,notes,created_at) VALUES(?,?,?,?,?,?,?)",
                         (request.form.get("rule_name"), request.form.get("match_text"), request.form.get("category"), request.form.get("entry_type"), 1, request.form.get("notes"), now_iso()))
            conn.commit(); flash("Bookkeeping rule saved.", "success")
        return redirect(url_for("bookkeeping"))
    snap = bookkeeping_snapshot(conn)
    ledgers = conn.execute("SELECT bl.*, j.job_name FROM bookkeeping_ledgers bl LEFT JOIN jobs j ON j.id=bl.job_id ORDER BY COALESCE(bl.entry_date,'') DESC, bl.id DESC LIMIT 150").fetchall()
    rules = conn.execute("SELECT * FROM bookkeeping_rules ORDER BY active DESC, rule_name").fetchall()
    runs = conn.execute("SELECT * FROM bookkeeping_runs ORDER BY run_time DESC LIMIT 10").fetchall()
    ledger_rows = ''.join(f"<tr><td>{html.escape(r['entry_date'] or '')}</td><td>{html.escape(r['entry_type'] or '')}</td><td>{html.escape(r['category'] or '')}</td><td>{html.escape(r['job_name'] or 'Overhead')}</td><td>{money(r['debit'] or 0)}</td><td>{money(r['credit'] or 0)}</td><td>{html.escape(r['receipt_status'] or '')}</td><td>{html.escape(r['status'] or '')}</td></tr>" for r in ledgers)
    rule_rows = ''.join(f"<tr><td>{html.escape(r['rule_name'] or '')}</td><td>{html.escape(r['match_text'] or '')}</td><td>{html.escape(r['category'] or '')}</td><td>{html.escape(r['entry_type'] or '')}</td><td>{'Yes' if r['active'] else 'No'}</td></tr>" for r in rules)
    run_rows = ''.join(f"<tr><td>{html.escape(r['run_time'] or '')}</td><td>{money(r['total_income'] or 0)}</td><td>{money(r['total_expenses'] or 0)}</td><td>{money(r['total_worker_pay'] or 0)}</td><td>{r['missing_receipts'] or 0}</td><td>{r['duplicate_file_names'] or 0}</td><td>{html.escape(r['notes'] or '')}</td></tr>" for r in runs)
    body = f"""
    <div class='grid'>
      <div class='stat'>Cash-Basis Income<b>{money(snap['income'])}</b></div>
      <div class='stat'>Known Expenses<b>{money(snap['expenses'])}</b></div>
      <div class='stat'>Worker Pay<b>{money(snap['worker_pay'])}</b></div>
      <div class='stat'>Worker Cost Fees<b>{money(snap['worker_fees'])}</b></div>
      <div class='stat'>Estimated Profit<b>{money(snap['profit_cash_basis'])}</b></div>
      <div class='stat'>Receivables<b>{money(snap['receivables'])}</b></div>
      <div class='stat'>Missing Receipts<b>{snap['missing_receipts']}</b></div>
      <div class='stat'>Duplicate File Names<b>{snap['duplicate_file_names']}</b></div>
    </div>
    <div class='card'><h2>Bookkeeping Control Center</h2><p class='muted'>This reconciles job income, expenses, worker payroll, worker cost fees, receipts, and file evidence into a bookkeeping ledger. It does not delete source records.</p>
      <form method='post'><input type='hidden' name='action' value='reconcile'><button>Reconcile Bookkeeping Now</button> <a class='btn btn2' href='/bookkeeping/export'>Export Bookkeeping CSV</a> <a class='btn btn2' href='/bookkeeping/summary'>Download Summary</a> <a class='btn btn2' href='/filekeeping'>Filekeeping</a> <a class='btn btn2' href='/files/refresh'>Refresh File Sources</a></form>
    </div>
    <div class='card'><h2>Add Bookkeeping Rule</h2><form method='post'><input type='hidden' name='action' value='add_rule'><div class='row3'><p><label>Rule Name</label><input name='rule_name'></p><p><label>Match Text</label><input name='match_text' placeholder='lowes, fuel, helper'></p><p><label>Category</label><input name='category' placeholder='Materials & Supplies'></p></div><div class='row'><p><label>Entry Type</label><select name='entry_type'><option>Expense</option><option>Income</option><option>File/Evidence</option></select></p><p><label>Notes</label><input name='notes'></p></div><button>Save Rule</button></form></div>
    <div class='card'><h2>Recent Ledger Rows</h2><table><tr><th>Date</th><th>Type</th><th>Category</th><th>Job</th><th>Debit/Cost</th><th>Credit/Income</th><th>Receipt</th><th>Status</th></tr>{ledger_rows}</table></div>
    <div class='card'><h2>Bookkeeping Rules</h2><table><tr><th>Rule</th><th>Match Text</th><th>Category</th><th>Type</th><th>Active</th></tr>{rule_rows}</table></div>
    <div class='card'><h2>Recent Reconciliation Runs</h2><table><tr><th>Run Time</th><th>Income</th><th>Expenses</th><th>Worker Pay</th><th>Missing Receipts</th><th>Duplicate Files</th><th>Notes</th></tr>{run_rows}</table></div>
    """
    return layout("Bookkeeping", body, "bookkeeping")
@app.route("/bookkeeping/summary")
@login_required("view_bookkeeping")
def bookkeeping_summary_report():
    ensure_bookkeeping_schema(); conn = db(); snap = bookkeeping_snapshot(conn); fsnap = filekeeping_snapshot(conn); EXPORT_DIR.mkdir(exist_ok=True)
    out = EXPORT_DIR / f"JRC_Bookkeeping_Filekeeping_Summary_{dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.txt"
    text = f"""J & R Construction - Bookkeeping and Filekeeping Summary
Generated: {now_display()}
BOOKKEEPING
Cash-basis income: {money(snap['income'])}
Known expenses: {money(snap['expenses'])}
Worker pay: {money(snap['worker_pay'])}
Worker cost fees: {money(snap['worker_fees'])}
Total known cost: {money(snap['total_cost'])}
Estimated profit: {money(snap['profit_cash_basis'])}
Receivables: {money(snap['receivables'])}
Open jobs: {snap['open_jobs']}
Missing receipt review count: {snap['missing_receipts']}
FILEKEEPING
Active file sources: {fsnap['source_count']}
Indexed files: {fsnap['indexed_files']}
Receipt/evidence-like files: {fsnap['receipt_like_files']}
Missing source paths: {fsnap['missing_source_paths']}
Duplicate filename groups: {fsnap['duplicate_file_names']}
Notes:
- Owner labor remains internal job costing only, not a deductible wage to the sole proprietor.
- Cash payments should still be tracked as business income when received.
- Review receipts and source files before tax filing.
"""
    out.write_text(text, encoding='utf-8')
    return send_file(out, as_attachment=True)
@app.route("/bookkeeping/export")
@login_required("view_bookkeeping")
def bookkeeping_export():
    ensure_bookkeeping_schema(); EXPORT_DIR.mkdir(exist_ok=True)
    out = EXPORT_DIR / f"JRC_Bookkeeping_Ledger_{dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv"
    rows = db().execute("SELECT bl.*, j.job_name FROM bookkeeping_ledgers bl LEFT JOIN jobs j ON j.id=bl.job_id ORDER BY COALESCE(bl.entry_date,'') DESC, bl.id DESC").fetchall()
    import csv
    with out.open('w', newline='', encoding='utf-8') as f:
        w=csv.writer(f); w.writerow(['entry_date','entry_type','category','job_name','source_table','source_id','description','debit_cost','credit_income','status','receipt_status','notes'])
        for r in rows:
            w.writerow([r['entry_date'],r['entry_type'],r['category'],r['job_name'],r['source_table'],r['source_id'],r['description'],r['debit'],r['credit'],r['status'],r['receipt_status'],r['notes']])
    flash(f"Bookkeeping ledger exported: {out.name}", "success")
    return redirect(url_for("bookkeeping"))
@app.route("/payroll", methods=["GET", "POST"])
@login_required("view_workers")
def payroll():
    conn = db(); ensure_payroll_schema()
    user = current_user(); perms = get_user_permissions(user["id"], user["role"])
    if request.method == "POST":
        if "manage_payroll" not in perms and "edit_workers" not in perms:
            abort(403)
        worker_id = request.form.get("worker_id") or None
        job_id = request.form.get("job_id") or None
        hours = parse_float(request.form.get("hours"))
        rate = parse_float(request.form.get("rate"))
        amount = parse_float(request.form.get("amount"))
        if amount <= 0 and hours > 0 and rate > 0:
            amount = hours * rate
        cost_fee = parse_float(request.form.get("cost_fee"))
        if cost_fee <= 0 and request.form.get("add_default_fee") == "yes":
            cost_fee = 100.0
        status = request.form.get("status") or "Pending"
        paid_at = now_iso() if status == "Paid" else None
        conn.execute("""INSERT INTO worker_payments(worker_id, job_id, work_date, description, amount, payment_method, status, notes, created_at, hours, rate, cost_fee, approved_by, approved_at, paid_at, source)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (worker_id, job_id, request.form.get("work_date") or dt.date.today().isoformat(), request.form.get("description"), amount, request.form.get("payment_method"), status, request.form.get("notes"), now_iso(), hours, rate, cost_fee, user["username"], now_iso() if status in ["Approved","Paid"] else None, paid_at, "payroll-center"))
        conn.commit(); log_event("Payroll", f"Logged worker payroll {money(amount)} plus cost fee {money(cost_fee)}")
        flash("Payroll entry saved and job costs updated.", "success")
        return redirect(url_for("payroll"))
    workers = conn.execute("SELECT id, name, default_rate, classification FROM workers WHERE active=1 ORDER BY name").fetchall()
    jobs = conn.execute("SELECT id, job_name FROM jobs ORDER BY updated_at DESC, id DESC").fetchall()
    worker_opts = ''.join(f'<option value="{w["id"]}" data-rate="{w["default_rate"] or 0}">{html.escape(w["name"])} - {money(w["default_rate"] or 0)}</option>' for w in workers)
    job_opts = '<option value="">No job / overhead</option>' + ''.join(f'<option value="{j["id"]}">{html.escape(j["job_name"])}</option>' for j in jobs)
    rows = conn.execute("""SELECT wp.*, w.name worker_name, j.job_name FROM worker_payments wp
                           LEFT JOIN workers w ON w.id=wp.worker_id LEFT JOIN jobs j ON j.id=wp.job_id
                           ORDER BY COALESCE(wp.work_date,'') DESC, wp.id DESC LIMIT 200""").fetchall()
    total_paid = conn.execute("SELECT COALESCE(SUM(amount),0), COALESCE(SUM(COALESCE(cost_fee,0)),0), COALESCE(SUM(COALESCE(hours,0)),0) FROM worker_payments WHERE status='Paid'").fetchone()
    trs = ''.join(f"<tr><td>{html.escape(r['work_date'] or '')}</td><td>{html.escape(r['worker_name'] or '')}</td><td>{html.escape(r['job_name'] or 'Overhead')}</td><td>{html.escape(str(r['hours'] or ''))}</td><td>{money(r['rate'] or 0)}</td><td>{money(r['amount'] or 0)}</td><td>{money(r['cost_fee'] or 0)}</td><td><span class='badge'>{html.escape(r['status'] or '')}</span></td><td>{html.escape(r['payment_method'] or '')}</td></tr>" for r in rows)
    body = f"""
    <div class='grid'>
      <div class='stat'>Paid Worker Pay<b>{money(total_paid[0])}</b></div>
      <div class='stat'>Worker Cost Fees<b>{money(total_paid[1])}</b></div>
      <div class='stat'>Paid Hours<b>{float(total_paid[2] or 0):,.2f}</b></div>
    </div>
    <div class='card'><h2>Log Worker Payroll</h2><form method='post'>
      <div class='row3'><p><label>Worker</label><select name='worker_id'>{worker_opts}</select></p><p><label>Job</label><select name='job_id'>{job_opts}</select></p><p><label>Work Date</label><input name='work_date' value='{dt.date.today().isoformat()}'></p></div>
      <div class='row3'><p><label>Hours</label><input name='hours' placeholder='8'></p><p><label>Rate</label><input name='rate' placeholder='140 day or hourly rate'></p><p><label>Amount Paid / Owed</label><input name='amount' placeholder='140'></p></div>
      <div class='row3'><p><label>Payment Method</label><input name='payment_method' placeholder='Cash, Cash App, Check'></p><p><label>Status</label><select name='status'><option>Pending</option><option>Approved</option><option selected>Paid</option><option>Cancelled</option></select></p><p><label>Cost Fee</label><input name='cost_fee' placeholder='100'><label><input type='checkbox' name='add_default_fee' value='yes'> Add default $100 worker cost fee</label></p></div>
      <p><label>Work Description</label><textarea name='description' placeholder='What did the worker do?'></textarea></p><p><label>Notes</label><textarea name='notes'></textarea></p>
      <button>Save Payroll Entry</button> <a class='btn btn2' href='/payroll/export'>Export Payroll CSV</a>
    </form><p class='muted'>Payroll entries automatically feed job costs, worker totals, and tax prep reports. Final payroll/tax filing should still be reviewed by a tax professional.</p></div>
    <div class='card'><h2>Recent Payroll Entries</h2><table><tr><th>Date</th><th>Worker</th><th>Job</th><th>Hours</th><th>Rate</th><th>Pay</th><th>Cost Fee</th><th>Status</th><th>Method</th></tr>{trs}</table></div>
    """
    return layout("Payroll", body, "payroll")
@app.route("/owner-draws", methods=["GET", "POST"])
@login_required("view_money")
def owner_draws_page():
    from app.owner_draws import (
        default_draw_account,
        default_office_daily_amount,
        default_work_type,
        ensure_owner_draws_schema,
        log_owner_draw,
        total_owner_draws,
    )
    conn = db()
    ensure_owner_draws_schema(conn)
    user = current_user()
    perms = get_user_permissions(user["id"], user["role"])
    std_amount = default_office_daily_amount(conn)
    std_account = default_draw_account(conn)
    std_work = default_work_type(conn)
    if request.method == "POST":
        if "manage_payroll" not in perms and "edit_workers" not in perms and "view_bookkeeping" not in perms:
            abort(403)
        amount = parse_float(request.form.get("amount"))
        if amount <= 0:
            amount = std_amount
        job_id_raw = request.form.get("job_id") or None
        job_id = int(job_id_raw) if job_id_raw else None
        draw_id = log_owner_draw(
            conn,
            draw_date=request.form.get("draw_date") or dt.date.today().isoformat(),
            amount=amount,
            description=request.form.get("description") or std_work,
            paid_from_account=request.form.get("paid_from_account") or std_account,
            payment_method=request.form.get("payment_method") or "",
            work_type=request.form.get("work_type") or std_work,
            job_id=job_id,
            notes=request.form.get("notes") or "",
            source="owner-draws-center",
        )
        log_event("Owner Draw", f"Logged owner draw {money(amount)} id={draw_id}")
        flash("Owner draw saved. This is an equity distribution, not a deductible expense.", "success")
        return redirect(url_for("owner_draws_page"))
    jobs = conn.execute("SELECT id, job_name FROM jobs ORDER BY updated_at DESC, id DESC").fetchall()
    job_opts = '<option value="">Overhead / no job</option>' + ''.join(
        f'<option value="{j["id"]}">{html.escape(j["job_name"])}</option>' for j in jobs
    )
    rows = conn.execute(
        """SELECT od.*, j.job_name FROM owner_draws od
           LEFT JOIN jobs j ON j.id=od.job_id
           ORDER BY COALESCE(od.draw_date,'') DESC, od.id DESC LIMIT 200"""
    ).fetchall()
    total = total_owner_draws(conn)
    trs = ''.join(
        f"<tr><td>{html.escape(r['draw_date'] or '')}</td><td>{money(r['amount'] or 0)}</td>"
        f"<td>{html.escape(r['paid_from_account'] or '')}</td><td>{html.escape(r['description'] or '')}</td>"
        f"<td>{html.escape(r['work_type'] or '')}</td><td>{html.escape(r['job_name'] or 'Overhead')}</td>"
        f"<td>{html.escape(r['payment_method'] or '')}</td></tr>"
        for r in rows
    )
    body = f"""
    <div class='grid'>
      <div class='stat'>Total Owner Draws<b>{money(total)}</b></div>
      <div class='stat'>Standard Office Day<b>{money(std_amount)}</b></div>
      <div class='stat'>Default Account<b>{html.escape(std_account)}</b></div>
    </div>
    <div class='card'><h2>Log Paid Myself (Owner Draw)</h2>
    <p class='muted'>Owner draws from business checking are equity distributions for a sole proprietor — not helper payroll and not deductible Schedule C expenses. Tell Cursor anytime you pay yourself and it will log here.</p>
    <form method='post'>
      <div class='row3'><p><label>Date</label><input name='draw_date' value='{dt.date.today().isoformat()}'></p>
      <p><label>Amount</label><input name='amount' value='{std_amount:.2f}' placeholder='{std_amount:.2f}'></p>
      <p><label>Paid From Account</label><input name='paid_from_account' value='{html.escape(std_account)}'></p></div>
      <div class='row3'><p><label>Work Type</label><input name='work_type' value='{html.escape(std_work)}'></p>
      <p><label>Description</label><input name='description' value='{html.escape(std_work)}'></p>
      <p><label>Payment Method</label><input name='payment_method' placeholder='Transfer, check, debit'></p></div>
      <p><label>Job (optional)</label><select name='job_id'>{job_opts}</select></p>
      <p><label>Notes</label><textarea name='notes' placeholder='Optional notes'></textarea></p>
      <button>Save Owner Draw</button> <a class='btn btn2' href='/owner-draws/export'>Export Owner Draws CSV</a>
    </form></div>
    <div class='card'><h2>Recent Owner Draws</h2><table><tr><th>Date</th><th>Amount</th><th>Account</th><th>Description</th><th>Work Type</th><th>Job</th><th>Method</th></tr>{trs}</table></div>
    """
    return layout("Owner Draws", body, "owner-draws")
@app.route("/owner-draws/export")
@login_required("view_money")
def owner_draws_export():
    from app.owner_draws import ensure_owner_draws_schema, export_owner_draws_csv
    ensure_owner_draws_schema(db())
    out = EXPORT_DIR / f"JRC_Owner_Draws_{dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv"
    export_owner_draws_csv(db(), out)
    log_event("Owner Draw", f"Exported owner draws CSV {out.name}")
    return send_file(out, as_attachment=True)
@app.route("/payroll/export")
@login_required("view_workers")
def payroll_export():
    ensure_payroll_schema(); out = EXPORT_DIR / f"JRC_Payroll_Job_Cost_Export_{dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv"
    rows = db().execute("""SELECT wp.id, wp.work_date, w.name worker, j.job_name, wp.hours, wp.rate, wp.amount, COALESCE(wp.cost_fee,0) cost_fee, wp.payment_method, wp.status, wp.description, wp.notes, wp.created_at
                           FROM worker_payments wp LEFT JOIN workers w ON w.id=wp.worker_id LEFT JOIN jobs j ON j.id=wp.job_id ORDER BY wp.work_date DESC, wp.id DESC""").fetchall()
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f); writer.writerow(["id","work_date","worker","job","hours","rate","amount","cost_fee","payment_method","status","description","notes","created_at"])
        for r in rows: writer.writerow([r[k] for k in r.keys()])
    log_event("Payroll", f"Exported payroll CSV {out.name}")
    return send_file(out, as_attachment=True)
@app.route("/job-costs")
@login_required("view_money")
def job_costs():
    conn = db(); ensure_payroll_schema()
    jobs = conn.execute("SELECT id, job_name, status, price, deposit, paid FROM jobs ORDER BY updated_at DESC, id DESC").fetchall()
    rows = []
    totals = {"revenue":0,"paid":0,"expenses":0,"worker_pay":0,"cost_fees":0,"total_cost":0,"profit":0,"balance":0}
    for j in jobs:
        c = job_cost_row(conn, j["id"])
        for k in totals: totals[k] += c[k]
        rows.append(f"<tr><td>{j['id']}</td><td>{html.escape(j['job_name'])}<br><span class='muted'>{html.escape(j['status'] or '')}</span></td><td>{money(c['revenue'])}</td><td>{money(c['paid'])}</td><td>{money(c['balance'])}</td><td>{money(c['expenses'])}</td><td>{money(c['worker_pay'])}</td><td>{money(c['cost_fees'])}</td><td>{money(c['total_cost'])}</td><td>{money(c['profit'])}</td></tr>")
    body = f"""
    <div class='grid'><div class='stat'>Revenue<b>{money(totals['revenue'])}</b></div><div class='stat'>Paid/Received<b>{money(totals['paid'])}</b></div><div class='stat'>Known Costs<b>{money(totals['total_cost'])}</b></div><div class='stat'>Est. Profit<b>{money(totals['profit'])}</b></div></div>
    <div class='card'><h2>Job Cost Dashboard</h2><p><a class='btn' href='/job-costs/export'>Export Job Cost CSV</a> <a class='btn btn2' href='/payroll'>Open Payroll</a></p><table><tr><th>ID</th><th>Job</th><th>Price</th><th>Paid</th><th>Balance</th><th>Expenses</th><th>Worker Pay</th><th>Worker Fees</th><th>Total Cost</th><th>Est. Profit</th></tr>{''.join(rows)}</table></div>
    <div class='card'><h2>Checks and Balances</h2><ul><li>Worker payroll feeds job cost totals automatically.</li><li>Expenses feed job cost totals automatically.</li><li>Job paid amount and invoice payments should be reconciled during closeout.</li><li>Owner labor remains internal job-costing only and is not counted as a paid worker expense.</li></ul></div>
    """
    return layout("Job Costs", body, "accounting")
@app.route("/job-costs/export")
@login_required("view_money")
def job_costs_export():
    conn = db(); ensure_payroll_schema(); out = EXPORT_DIR / f"JRC_Job_Cost_Dashboard_{dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv"
    jobs = conn.execute("SELECT id, job_name, status FROM jobs ORDER BY id").fetchall()
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f); writer.writerow(["job_id","job_name","status","price","paid","balance","expenses","worker_pay","worker_cost_fees","total_known_cost","estimated_profit"])
        for j in jobs:
            c = job_cost_row(conn, j["id"]); writer.writerow([j["id"], j["job_name"], j["status"], c["revenue"], c["paid"], c["balance"], c["expenses"], c["worker_pay"], c["cost_fees"], c["total_cost"], c["profit"]])
    log_event("Accounting", f"Exported job cost CSV {out.name}")
    return send_file(out, as_attachment=True)
@app.route("/apply", methods=["GET", "POST"])
def public_job_application():
    """Public worker/job application form. Does not create login access until owner/admin approval."""
    ensure_job_application_schema()
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        desired_username = request.form.get("requested_username", "").strip().lower()
        if not full_name or not phone:
            flash("Full name and phone are required.", "error")
        elif not email:
            flash("Email is required so we can send you application status updates.", "error")
        else:
            conn = db()
            status_token = secrets.token_urlsafe(24)
            cur = conn.execute("""INSERT INTO job_applications(
                created_at,updated_at,status,requested_username,desired_role,full_name,email,recovery_email,phone,address,date_of_birth,
                emergency_contact_name,emergency_contact_phone,preferred_rate,rate_type,availability,transportation,drivers_license_status,
                own_tools,skills,experience_years,work_history,references_text,insurance_full_legal_name,insurance_address,insurance_phone,
                insurance_email,insurance_date_of_birth,insurance_driver_license_state,insurance_driver_license_number,insurance_vehicle_use,
                insurance_employment_classification,insurance_requested_coverage,insurance_notes,w9_status,id_document_status,request_ip,request_user_agent,status_token)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (now_iso(), now_iso(), "Pending Owner Review", desired_username, request.form.get("desired_role") or "worker", full_name, email,
                 request.form.get("recovery_email"), phone, request.form.get("address"), request.form.get("date_of_birth"), request.form.get("emergency_contact_name"),
                 request.form.get("emergency_contact_phone"), parse_float(request.form.get("preferred_rate")), request.form.get("rate_type") or "daily",
                 request.form.get("availability"), request.form.get("transportation"), request.form.get("drivers_license_status"), request.form.get("own_tools"),
                 request.form.get("skills"), parse_float(request.form.get("experience_years")), request.form.get("work_history"), request.form.get("references_text"),
                 request.form.get("insurance_full_legal_name") or full_name, request.form.get("insurance_address") or request.form.get("address"),
                 request.form.get("insurance_phone") or phone, request.form.get("insurance_email") or email, request.form.get("insurance_date_of_birth") or request.form.get("date_of_birth"),
                 request.form.get("insurance_driver_license_state"), request.form.get("insurance_driver_license_number"), request.form.get("insurance_vehicle_use"),
                 request.form.get("insurance_employment_classification") or "Needs owner review", request.form.get("insurance_requested_coverage"),
                 request.form.get("insurance_notes"), request.form.get("w9_status") or "Needed if paid as contractor", request.form.get("id_document_status") or "Not received",
                 client_ip(), request.headers.get("User-Agent", ""), status_token))
            app_id = cur.lastrowid
            conn.commit()
            log_application_event(app_id, "submitted", f"Application submitted by {full_name}", full_name)
            log_security_event("job_application_submitted", desired_username or full_name, f"Application #{app_id} submitted — owner notified", "INFO")
            try:
                from app.application_notifications import notify_owner_new_application

                ok, note = notify_owner_new_application(conn, int(app_id), request_base_url=request.url_root.rstrip("/"))
                log_application_event(app_id, "owner_notified", note, "system")
            except Exception as exc:
                log_application_event(app_id, "owner_notify_error", str(exc), "system")
            flash("Application submitted and sent to Jacob for owner review. Check your email for status updates.", "success")
            return redirect(url_for("public_job_application_thanks", app_id=app_id, token=status_token))
    body = """
    <div class='card'><h2>J & R Construction Worker / Job Application</h2><p class='muted'>Applications go directly to Jacob (owner) for review. You will receive email status updates when your application is reviewed. This does not guarantee work, employment, insurance coverage, or account access.</p></div>
    <form method='post'>
    <div class='card'><h2>Basic Information</h2><div class='row'>
      <label>Full legal name<input name='full_name' required></label><label>Desired username<input name='requested_username'></label>
      <label>Email<input name='email' type='email' required placeholder='Required for status updates'></label><label>Recovery email<input name='recovery_email' type='email'></label>
      <label>Phone<input name='phone' required></label><label>Date of birth<input name='date_of_birth' placeholder='YYYY-MM-DD'></label>
      <label>Address<textarea name='address'></textarea></label><label>Desired role<select name='desired_role'>
        <option value='helper'>Field Helper (W-2 employee candidate)</option>
        <option value='worker'>Company Employee</option>
        <option value='subcontractor'>Subcontractor / 1099</option>
        <option value='viewer'>Office read-only staff</option>
      </select></label>
    </div></div>
    <div class='card'><h2>Worker Details</h2><div class='row'>
      <label>Preferred rate<input name='preferred_rate' placeholder='140'></label><label>Rate type<select name='rate_type'><option>daily</option><option>hourly</option><option>job-based</option></select></label>
      <label>Availability<textarea name='availability'></textarea></label><label>Transportation<textarea name='transportation'></textarea></label>
      <label>Driver license status<textarea name='drivers_license_status'></textarea></label><label>Own tools / equipment<textarea name='own_tools'></textarea></label>
      <label>Skills<textarea name='skills' placeholder='Carpentry, flooring, demo, painting, helper, etc.'></textarea></label><label>Years of experience<input name='experience_years'></label>
      <label>Work history<textarea name='work_history'></textarea></label><label>References<textarea name='references_text'></textarea></label>
      <label>Emergency contact name<input name='emergency_contact_name'></label><label>Emergency contact phone<input name='emergency_contact_phone'></label>
    </div></div>
    <div class='card'><h2>Insurance / Policy Onboarding Information</h2><p class='muted'>This helps Jacob prepare questions for insurance, worker classification, jobsite access, and coverage review. Do not enter SSN here.</p><div class='row'>
      <label>Insurance full legal name<input name='insurance_full_legal_name'></label><label>Insurance phone<input name='insurance_phone'></label>
      <label>Insurance email<input name='insurance_email'></label><label>Insurance date of birth<input name='insurance_date_of_birth' placeholder='YYYY-MM-DD'></label>
      <label>Insurance address<textarea name='insurance_address'></textarea></label><label>Driver license state<input name='insurance_driver_license_state'></label>
      <label>Driver license number<input name='insurance_driver_license_number'></label><label>Vehicle use for J&R work<textarea name='insurance_vehicle_use'></textarea></label>
      <label>Worker classification requested<select name='insurance_employment_classification'><option>Needs owner review</option><option>Employee candidate</option><option>Independent contractor candidate</option><option>Occasional helper</option></select></label><label>Coverage requested / job duties<textarea name='insurance_requested_coverage'></textarea></label>
      <label>W-9 / tax form status<select name='w9_status'><option>Needed if paid as contractor</option><option>Provided</option><option>Not applicable yet</option></select></label><label>ID document status<select name='id_document_status'><option>Not received</option><option>Viewed by owner</option><option>Provided separately</option></select></label>
      <label>Insurance notes<textarea name='insurance_notes'></textarea></label>
    </div></div>
    <div class='card'><button>Submit Application for Owner Review</button> <a class='btn btn2' href='/register'>Request login only (no application)</a> <a class='btn btn2' href='/login'>Already have an account — Sign In</a></div>
    </form>"""
    return layout("Worker Application", body, "apply", public=True)
@app.route("/apply/thanks/<int:app_id>")
def public_job_application_thanks(app_id: int):
    token = request.args.get("token", "")
    status_link = ""
    if token:
        status_link = f"<p><a class='btn' href='/apply/status/{app_id}/{html.escape(token)}'>Check application status</a></p>"
    body = f"""<div class='card'><h2>Application Received — Owner Review Queue</h2>
    <p>Your application number is <b>#{app_id}</b>.</p>
    <p class='muted'>A copy was sent to Jacob for owner review. You will receive email updates when the status changes.</p>
    {status_link}
    <p><a class='btn btn2' href='/login'>Sign In</a> <a class='btn btn2' href='/register'>Request Account</a></p></div>"""
    return layout("Application Received", body, "apply", public=True)


@app.route("/apply/status/<int:app_id>/<token>")
def public_job_application_status(app_id: int, token: str):
    ensure_job_application_schema()
    row = db().execute(
        "SELECT id, full_name, status, owner_notes, reviewed_at, reviewed_by, created_at, updated_at, "
        "applicant_notified_status, applicant_notified_at FROM job_applications WHERE id=? AND status_token=?",
        (app_id, token),
    ).fetchone()
    if not row:
        body = "<div class='card'><h2>Application not found</h2><p class='muted'>Invalid or expired status link.</p><p><a href='/apply'>Submit a new application</a></p></div>"
        return layout("Application Status", body, "apply", public=True)
    events = db().execute(
        "SELECT event_time, event_type, message FROM application_events WHERE application_id=? ORDER BY id DESC LIMIT 12",
        (app_id,),
    ).fetchall()
    ev_rows = "".join(
        f"<tr><td>{html.escape(e['event_time'] or '')}</td><td>{html.escape(e['event_type'] or '')}</td>"
        f"<td>{html.escape(e['message'] or '')}</td></tr>"
        for e in events
    )
    visible_notes = (row["owner_notes"] or "").strip()
    notes_html = f"<p><b>Owner message:</b> {html.escape(visible_notes)}</p>" if visible_notes else ""
    body = f"""<div class='card'><h2>Application #{app_id} Status</h2>
    <p><b>{html.escape(row['full_name'] or '')}</b></p>
    <div class='stat'>Current status<b>{html.escape(row['status'] or '')}</b></div>
    <p class='muted'>Submitted: {html.escape(row['created_at'] or '')} | Last update: {html.escape(row['updated_at'] or '')}</p>
    {notes_html}
  </div>
  <div class='card'><h2>Update history</h2>
    <table><tr><th>When</th><th>Event</th><th>Detail</th></tr>{ev_rows or '<tr><td colspan=3>No events yet.</td></tr>'}</table>
  </div>"""
    return layout("Application Status", body, "apply", public=True)


@app.route("/applications", methods=["GET", "POST"])
@login_required("view_applications")
def applications_center():
    ensure_job_application_schema()
    conn = db(); user = current_user(); perms = get_user_permissions(user["id"], user["role"])
    if request.method == "POST":
        if "manage_applications" not in perms:
            abort(403)
        aid = int(request.form.get("application_id") or 0)
        action = request.form.get("action") or ""
        notes = request.form.get("owner_notes", "")
        if action in {"review", "approve", "deny", "needs_info"}:
            status = {"review":"Under Owner Review", "approve":"Approved for Onboarding", "deny":"Denied", "needs_info":"Needs More Information"}[action]
            conn.execute("UPDATE job_applications SET status=?, owner_notes=?, reviewed_by=?, reviewed_at=?, updated_at=? WHERE id=?",
                         (status, notes, user["username"], now_iso(), now_iso(), aid))
            if action == "approve" and "manage_applications" in perms:
                app_row = conn.execute("SELECT * FROM job_applications WHERE id=?", (aid,)).fetchone()
                if app_row:
                    uname = (app_row["requested_username"] or "").strip().lower()
                    hire_role = normalize_role_for_session(app_row["desired_role"] or "helper")
                    if hire_role not in HIRE_APPLICATION_ROLES:
                        hire_role = "helper"
                    if uname and not conn.execute("SELECT id FROM users WHERE username=?", (uname,)).fetchone():
                        temp_pw = secrets.token_urlsafe(12)
                        salt, ph = hash_password(temp_pw)
                        cur = conn.execute(
                            """INSERT INTO users (username, display_name, role, salt, password_hash, active, must_change_password, created_at, notes, email, phone)
                               VALUES (?,?,?,?,?,1,1,?,?,?,?)""",
                            (uname, app_row["full_name"] or uname, hire_role, salt, ph, now_iso(),
                             f"Created from job application #{aid}. W-9: {app_row['w9_status'] or ''}",
                             app_row["email"] or "", app_row["phone"] or ""),
                        )
                        uid = int(cur.lastrowid)
                        from app.account_provisioning import provision_user_role_profiles
                        provision_user_role_profiles(db(), uid, uname, hire_role)
                        conn.execute("UPDATE job_applications SET approved_user_id=? WHERE id=?", (uid, aid))
                        log_application_event(aid, "account_created", f"User {uname} created as {hire_role}", user["username"])
                        flash(f"Application approved. Account created: {uname} | temporary password: {temp_pw} (user must change on first login).", "success")
            try:
                from app.application_notifications import notify_applicant_status_update

                n_ok, n_msg = notify_applicant_status_update(
                    conn, aid, status, notes, request_base_url=request.url_root.rstrip("/")
                )
                log_application_event(aid, "applicant_notified", n_msg, user["username"])
                if n_ok:
                    flash(f"Applicant emailed: {status}", "success")
                elif "no email" not in n_msg.lower():
                    flash(f"Applicant notification: {n_msg}", "warning")
            except Exception as exc:
                log_application_event(aid, "applicant_notify_error", str(exc), user["username"])
            conn.commit(); log_application_event(aid, action, f"Status changed to {status}", user["username"]); log_event("Applications", f"Application #{aid} set to {status}")
        return redirect(url_for("applications_center"))
    apps = conn.execute("SELECT * FROM job_applications ORDER BY CASE status WHEN 'Pending Owner Review' THEN 0 WHEN 'Under Owner Review' THEN 1 WHEN 'Needs More Information' THEN 2 ELSE 3 END, created_at DESC").fetchall()
    public_link = url_for('public_job_application', _external=True)
    rows=[]
    for a in apps:
        action_html = ""
        if "manage_applications" in perms:
            action_html = f"""<form method='post'><input type='hidden' name='application_id' value='{a['id']}'><textarea name='owner_notes' placeholder='Owner notes'>{html.escape(a['owner_notes'] or '')}</textarea><button name='action' value='review'>Review</button> <button name='action' value='approve'>Approve</button> <button class='warn' name='action' value='needs_info'>Need Info</button> <button class='danger' name='action' value='deny'>Deny</button></form>"""
        rows.append(f"""<tr><td><b>#{a['id']} {html.escape(a['full_name'] or '')}</b><br><span class='badge'>{html.escape(a['status'] or '')}</span><br><span class='muted'>User: {html.escape(a['requested_username'] or '')}</span></td><td>{html.escape(a['phone'] or '')}<br>{html.escape(a['email'] or '')}<br><span class='muted'>{html.escape(a['address'] or '')}</span></td><td>{html.escape(a['skills'] or '')}<br><span class='muted'>Rate: {money(a['preferred_rate'])} {html.escape(a['rate_type'] or '')}</span></td><td>{html.escape(a['insurance_employment_classification'] or '')}<br><span class='muted'>DL: {html.escape(a['insurance_driver_license_state'] or '')} {html.escape(a['insurance_driver_license_number'] or '')}</span><br>W-9: {html.escape(a['w9_status'] or '')}<br>ID: {html.escape(a['id_document_status'] or '')}</td><td>{html.escape(a['request_ip'] or '')}<br><span class='muted'>{html.escape((a['request_user_agent'] or '')[:60])}</span></td><td>{action_html}</td></tr>""")
    from app.application_notifications import get_owner_email

    owner_email = get_owner_email(conn)
    pending = conn.execute("SELECT COUNT(*) FROM job_applications WHERE status IN ('Pending Owner Review','Under Owner Review','Needs More Information')").fetchone()[0]
    body = f"""<div class='card'><h2>Worker Applications — Owner Review Queue</h2>
    <p>New applications email <b>{html.escape(owner_email)}</b> automatically. Applicants receive email when you update status here.</p>
    <p class='muted'>Pending / in review: <b>{pending}</b> | Copies also saved to <code>data/application_email_outbox/</code> and Dropbox <code>03_BUSINESS_ADMIN/Job_Application_Inbox/</code></p>
    <p>Share this public link (no install needed):</p><p><input value='{html.escape(public_link)}' readonly onclick='this.select()'></p>
    <p><a class='btn' href='{html.escape(public_link)}' target='_blank'>Open Application Form</a> <a class='btn btn2' href='/applications/export'>Export CSV</a> <a class='btn btn2' href='/admin'>Admin</a></p>
    <p class='muted'>Set <code>JRC_SMTP_USER</code> + <code>JRC_SMTP_PASSWORD</code> (Outlook app password) for live email send. Without SMTP, inbox file copies are still created every submit.</p></div>
    <div class='card'><h2>Applications</h2><table><tr><th>Applicant</th><th>Contact</th><th>Work Info</th><th>Insurance / Onboarding</th><th>Source</th><th>Owner Review</th></tr>{''.join(rows)}</table></div>"""
    return layout("Applications", body, "applications")
@app.route("/applications/export")
@login_required("view_applications")
def applications_export():
    ensure_job_application_schema(); EXPORT_DIR.mkdir(exist_ok=True)
    out = EXPORT_DIR / f"JRC_Worker_Job_Applications_Owner_Review_{dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv"
    rows = db().execute("SELECT * FROM job_applications ORDER BY created_at DESC").fetchall()
    with out.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['id','status','created_at','reviewed_at','reviewed_by','full_name','requested_username','phone','email','address','preferred_rate','rate_type','skills','transportation','drivers_license_status','insurance_full_legal_name','insurance_address','insurance_phone','insurance_email','insurance_date_of_birth','insurance_driver_license_state','insurance_driver_license_number','insurance_vehicle_use','insurance_employment_classification','insurance_requested_coverage','w9_status','id_document_status','owner_notes','request_ip'])
        for r in rows:
            writer.writerow([r[k] if k in r.keys() else '' for k in ['id','status','created_at','reviewed_at','reviewed_by','full_name','requested_username','phone','email','address','preferred_rate','rate_type','skills','transportation','drivers_license_status','insurance_full_legal_name','insurance_address','insurance_phone','insurance_email','insurance_date_of_birth','insurance_driver_license_state','insurance_driver_license_number','insurance_vehicle_use','insurance_employment_classification','insurance_requested_coverage','w9_status','id_document_status','owner_notes','request_ip']])
    log_event('Applications', f'Exported worker applications CSV {out.name}')
    return send_file(out, as_attachment=True)
@app.route("/customer")
@login_required("customer_portal")
def customer_home():
    user = current_user()
    role = normalize_role_for_session(user["role"] if user else "")
    if role != "customer":
        return redirect(url_for("dashboard"))
    return dashboard()
def ensure_customer_profile_for_current_user():
    user = current_user()
    row = db().execute("SELECT * FROM customer_user_profiles WHERE user_id=?", (user["id"],)).fetchone()
    if row:
        return row
    db().execute("""INSERT INTO customer_user_profiles (user_id, username, display_name, email, phone, address, created_at, updated_at, notes)
                  VALUES (?,?,?,?,?,?,?,?,?)""", (user["id"], user["username"], user["display_name"] or user["username"], user["email"] if "email" in user.keys() else "", user["phone"] if "phone" in user.keys() else "", "", now_iso(), now_iso(), "Auto-created by customer portal."))
    db().commit()
    return db().execute("SELECT * FROM customer_user_profiles WHERE user_id=?", (user["id"],)).fetchone()

def ensure_customer_request_schema():
    """Repair customer request columns so older installs can accept the latest customer portal form."""
    conn = db()
    conn.execute("""CREATE TABLE IF NOT EXISTS customer_job_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_user_id INTEGER,
        customer_id INTEGER,
        created_by_username TEXT,
        status TEXT DEFAULT 'Submitted',
        priority TEXT DEFAULT 'Normal',
        request_title TEXT,
        service_type TEXT,
        property_address TEXT,
        requested_timeline TEXT,
        access_notes TEXT,
        description TEXT,
        photos_notes TEXT,
        customer_visible_notes TEXT,
        internal_notes TEXT,
        submitted_at TEXT,
        updated_at TEXT,
        reviewed_at TEXT,
        reviewed_by TEXT,
        converted_job_id INTEGER,
        request_ip TEXT,
        request_user_agent TEXT
    )""")
    existing = {r[1] for r in conn.execute("PRAGMA table_info(customer_job_requests)").fetchall()}
    columns = {
        "contact_name": "TEXT",
        "contact_phone": "TEXT",
        "contact_email": "TEXT",
        "best_contact_method": "TEXT",
        "property_type": "TEXT",
        "occupancy_status": "TEXT",
        "tenant_name": "TEXT",
        "tenant_phone": "TEXT",
        "appointment_window": "TEXT",
        "safety_notes": "TEXT",
        "pets_notes": "TEXT",
        "budget_range": "TEXT",
        "request_reason": "TEXT",
        "customer_acknowledged": "INTEGER DEFAULT 0",
    }
    for name, col_type in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE customer_job_requests ADD COLUMN {name} {col_type}")
    conn.execute("""CREATE TABLE IF NOT EXISTS customer_request_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        event_time TEXT,
        event_type TEXT,
        username TEXT,
        message TEXT
    )""")
    conn.commit()

@app.route("/customer/request", methods=["GET", "POST"])
@login_required("customer_request_job")
def customer_request_job():
    ensure_customer_request_schema()
    profile = ensure_customer_profile_for_current_user()
    user = current_user()
    if request.method == "POST":
        title = request.form.get("request_title", "").strip()
        description = request.form.get("description", "").strip()
        address = request.form.get("property_address", "").strip()
        contact_name = request.form.get("contact_name", "").strip() or (profile["display_name"] if "display_name" in profile.keys() else session.get("username", ""))
        contact_phone = request.form.get("contact_phone", "").strip() or (profile["phone"] if "phone" in profile.keys() else "")
        contact_email = request.form.get("contact_email", "").strip() or (profile["email"] if "email" in profile.keys() else "")
        acknowledged = 1 if request.form.get("customer_acknowledged") else 0
        errors = []
        if not title:
            errors.append("Request title is required.")
        if not address:
            errors.append("Property address is required.")
        if not description:
            errors.append("Description of work needed is required.")
        if not contact_phone and not contact_email:
            errors.append("Please provide either a phone number or email so J&R can follow up.")
        if not acknowledged:
            errors.append("Please acknowledge that this is a request for owner review, not an approved job or final price.")
        if errors:
            for msg in errors:
                flash(msg, "error")
        else:
            fields = [
                "customer_user_id", "customer_id", "created_by_username", "status", "priority", "request_title", "service_type", "property_address", "requested_timeline", "access_notes", "description", "photos_notes", "customer_visible_notes", "submitted_at", "updated_at", "request_ip", "request_user_agent", "contact_name", "contact_phone", "contact_email", "best_contact_method", "property_type", "occupancy_status", "tenant_name", "tenant_phone", "appointment_window", "safety_notes", "pets_notes", "budget_range", "request_reason", "customer_acknowledged"
            ]
            values = [
                profile["id"], profile["customer_id"], session.get("username"), "Submitted", request.form.get("priority") or "Normal", title, request.form.get("service_type"), address, request.form.get("requested_timeline"), request.form.get("access_notes"), description, request.form.get("photos_notes"), "Request received by J&R Construction. Jacob/owner will review and follow up.", now_iso(), now_iso(), client_ip(), request.headers.get("User-Agent", ""), contact_name, contact_phone, contact_email, request.form.get("best_contact_method"), request.form.get("property_type"), request.form.get("occupancy_status"), request.form.get("tenant_name"), request.form.get("tenant_phone"), request.form.get("appointment_window"), request.form.get("safety_notes"), request.form.get("pets_notes"), request.form.get("budget_range"), request.form.get("request_reason"), acknowledged
            ]
            q = ",".join("?" for _ in fields)
            db().execute(f"INSERT INTO customer_job_requests ({','.join(fields)}) VALUES ({q})", values)
            req_id = db().execute("SELECT last_insert_rowid()").fetchone()[0]
            db().execute("INSERT INTO customer_request_events (request_id,event_time,event_type,username,message) VALUES (?,?,?,?,?)", (req_id, now_iso(), "submitted", session.get("username"), "Customer submitted a complete job request for owner review."))
            db().commit()
            flash("Job request submitted for J&R owner review. You can check its status from My Requests.", "success")
            return redirect(url_for("customer_request_detail", req_id=req_id))
    profile_name = html.escape(profile["display_name"] if "display_name" in profile.keys() and profile["display_name"] else (user["display_name"] or user["username"]))
    profile_phone = html.escape(profile["phone"] if "phone" in profile.keys() and profile["phone"] else "")
    profile_email = html.escape(profile["email"] if "email" in profile.keys() and profile["email"] else "")
    body = f"""
    <div class='card'><h2>New Job Request</h2><p class='muted'>Send J&R Construction the right information the first time. This creates a customer request for owner/admin review. It does not approve work, schedule the job, or set a final price automatically.</p></div>
    <form method='post'>
    <div class='grid'>
      <div class='card'><h2>1. Contact</h2>
        <p><label>Contact Name</label><input name='contact_name' value='{profile_name}' placeholder='Name of person J&R should contact'></p>
        <div class='row'><p><label>Phone</label><input name='contact_phone' value='{profile_phone}' placeholder='Best phone number'></p><p><label>Email</label><input name='contact_email' value='{profile_email}' placeholder='Email address'></p></div>
        <p><label>Best Contact Method</label><select name='best_contact_method'><option>Text message</option><option>Phone call</option><option>Email</option><option>Any is fine</option></select></p>
      </div>
      <div class='card'><h2>2. Property</h2>
        <p><label>Property Address</label><input name='property_address' required placeholder='Full job/property address'></p>
        <div class='row'><p><label>Property Type</label><select name='property_type'><option>House</option><option>Mobile home</option><option>Condo / townhome</option><option>Rental property</option><option>Commercial</option><option>Other</option></select></p><p><label>Occupancy</label><select name='occupancy_status'><option>Owner occupied</option><option>Tenant occupied</option><option>Vacant</option><option>Not sure</option></select></p></div>
        <div class='row'><p><label>Tenant / Site Contact Name</label><input name='tenant_name' placeholder='If different from you'></p><p><label>Tenant / Site Contact Phone</label><input name='tenant_phone' placeholder='If applicable'></p></div>
      </div>
    </div>
    <div class='card'><h2>3. Work Requested</h2>
      <div class='row'><p><label>Request Title</label><input name='request_title' required placeholder='Deck repair, flooring estimate, door issue'></p><p><label>Service Type</label><select name='service_type'><option>Estimate Request</option><option>Repair / Maintenance</option><option>Remodeling</option><option>Callback / Warranty Follow-up</option><option>Emergency / Urgent Review</option><option>Other</option></select></p></div>
      <div class='row'><p><label>Priority</label><select name='priority'><option>Normal</option><option>Urgent</option><option>Low</option></select></p><p><label>Why are you requesting this?</label><select name='request_reason'><option>New work / estimate</option><option>Existing job question</option><option>Repair needed</option><option>Water / leak concern</option><option>Safety concern</option><option>Warranty / callback</option><option>Other</option></select></p></div>
      <p><label>Description of Work Needed</label><textarea name='description' required placeholder='Describe the issue, what room/area it is in, what you want done, and any known damage.'></textarea></p>
      <p><label>Photos / Attachment Notes</label><textarea name='photos_notes' placeholder='Tell J&R what photos you have or will send: wide view, close-up, damage, measurements, access area, etc.'></textarea></p>
    </div>
    <div class='grid'>
      <div class='card'><h2>4. Access & Scheduling</h2>
        <p><label>Requested Timeline</label><input name='requested_timeline' placeholder='This week, next week, flexible, ASAP'></p>
        <p><label>Preferred Appointment Windows</label><input name='appointment_window' placeholder='Weekday mornings, after 3 PM, weekends, etc.'></p>
        <p><label>Access Notes</label><textarea name='access_notes' placeholder='Gate code, lockbox, tenant permission, parking, pets, preferred entry, etc.'></textarea></p>
      </div>
      <div class='card'><h2>5. Safety / Budget</h2>
        <p><label>Safety / Hazard Notes</label><textarea name='safety_notes' placeholder='Loose steps, mold, electrical concern, water damage, rotten floor, pets, occupied rental, etc.'></textarea></p>
        <p><label>Pets / Occupants Notes</label><textarea name='pets_notes' placeholder='Dogs, kids, tenant, someone home, alarm system, etc.'></textarea></p>
        <p><label>Budget Range / Approval Notes</label><input name='budget_range' placeholder='Optional: budget range, approval needed, insurance claim, etc.'></p>
      </div>
    </div>
    <div class='card'><label><input type='checkbox' name='customer_acknowledged' value='1' style='width:auto'> I understand this is a request for J&R owner review and not an approved job, schedule, or final price.</label><p><button>Submit Job Request</button> <a class='btn btn2' href='/customer'>Cancel</a></p></div>
    </form>
    """
    return layout("Create Customer Job Request", body, "customer")
@app.route("/customer/requests")
@login_required("customer_portal")
def customer_requests():
    ensure_customer_request_schema()
    profile = ensure_customer_profile_for_current_user()
    rows = db().execute("SELECT * FROM customer_job_requests WHERE customer_user_id=? ORDER BY submitted_at DESC, id DESC", (profile["id"],)).fetchall()
    html_rows = "".join(f"<tr><td>{r['id']}</td><td><a href='/customer/request/{r['id']}'>{html.escape(r['request_title'] or '')}</a></td><td>{html.escape(r['service_type'] or '')}</td><td>{html.escape(r['priority'] or '')}</td><td>{html.escape(r['status'] or '')}</td><td>{html.escape(r['submitted_at'] or '')}</td></tr>" for r in rows)
    body = f"""<div class='card'><h2>My Job Requests</h2><p class='muted'>Track requests you submitted to J&R Construction. New requests go to owner/admin review before scheduling or pricing.</p><p><a class='btn' href='/customer/request'>Create New Request</a></p><table><tr><th>ID</th><th>Request</th><th>Type</th><th>Priority</th><th>Status</th><th>Submitted</th></tr>{html_rows or '<tr><td colspan=6>No requests yet.</td></tr>'}</table></div>"""
    return layout("My Customer Requests", body, "customer")
@app.route("/customer/request/<int:req_id>")
@login_required("customer_portal")
def customer_request_detail(req_id:int):
    ensure_customer_request_schema()
    profile = ensure_customer_profile_for_current_user()
    r = db().execute("SELECT * FROM customer_job_requests WHERE id=? AND customer_user_id=?", (req_id, profile["id"])).fetchone()
    if not r:
        abort(404)
    events = db().execute("SELECT * FROM customer_request_events WHERE request_id=? ORDER BY event_time DESC, id DESC", (req_id,)).fetchall()
    event_rows = "".join(f"<tr><td>{html.escape(e['event_time'] or '')}</td><td>{html.escape(e['event_type'] or '')}</td><td>{html.escape(e['message'] or '')}</td></tr>" for e in events)
    body = f"""
    <div class='card'><h2>{html.escape(r['request_title'] or 'Customer Request')}</h2><div class='grid'><div class='stat'>Status<b>{html.escape(r['status'] or '')}</b></div><div class='stat'>Priority<b>{html.escape(r['priority'] or '')}</b></div><div class='stat'>Service<b>{html.escape(r['service_type'] or '')}</b></div></div>
    <p><b>Property:</b> {html.escape(r['property_address'] or '')}</p><p><b>Contact:</b> {html.escape(r['contact_name'] or '')} {html.escape(r['contact_phone'] or '')} {html.escape(r['contact_email'] or '')}</p><p><b>Timeline:</b> {html.escape(r['requested_timeline'] or '')}<br><b>Appointment Window:</b> {html.escape(r['appointment_window'] or '')}</p><p><b>Description:</b><br>{html.escape(r['description'] or '')}</p><p><b>Access Notes:</b><br>{html.escape(r['access_notes'] or '')}</p><p><b>Photos / Attachment Notes:</b><br>{html.escape(r['photos_notes'] or '')}</p><p><b>J&R Notes Visible to Customer:</b><br>{html.escape(r['customer_visible_notes'] or 'Request received by J&R Construction.')}</p></div>
    <div class='card'><h2>Request History</h2><table><tr><th>Time</th><th>Event</th><th>Message</th></tr>{event_rows or '<tr><td colspan=3>No events yet.</td></tr>'}</table></div>
    """
    return layout("Customer Request Detail", body, "customer")
@app.route("/customers/requests", methods=["GET", "POST"])
@login_required("manage_applications")
def owner_customer_requests():
    ensure_customer_request_schema()
    if request.method == "POST":
        req_id = int(request.form.get("req_id", "0") or 0)
        status = request.form.get("status", "Under Owner Review")
        visible = request.form.get("customer_visible_notes", "")
        internal = request.form.get("internal_notes", "")
        db().execute("UPDATE customer_job_requests SET status=?, customer_visible_notes=?, internal_notes=?, reviewed_at=?, reviewed_by=?, updated_at=? WHERE id=?", (status, visible, internal, now_iso(), session.get("username"), now_iso(), req_id))
        db().execute("INSERT INTO customer_request_events (request_id,event_time,event_type,username,message) VALUES (?,?,?,?,?)", (req_id, now_iso(), "owner_review", session.get("username"), f"Status changed to {status}."))
        db().commit()
        flash("Customer request updated.", "success")
    rows = db().execute("SELECT r.*, p.display_name, p.email, p.phone FROM customer_job_requests r LEFT JOIN customer_user_profiles p ON p.id=r.customer_user_id ORDER BY r.submitted_at DESC, r.id DESC").fetchall()
    row_html = "".join(f"<tr><td>{r['id']}</td><td>{html.escape(r['contact_name'] or r['display_name'] or r['created_by_username'] or '')}<br><span class='muted'>{html.escape(r['contact_phone'] or r['phone'] or '')} {html.escape(r['contact_email'] or r['email'] or '')}</span><br><span class='muted'>Preferred: {html.escape(r['best_contact_method'] or '')}</span></td><td><b>{html.escape(r['request_title'] or '')}</b><br><span class='muted'>{html.escape(r['property_address'] or '')}</span><br><span class='muted'>{html.escape(r['service_type'] or '')} • {html.escape(r['property_type'] or '')} • {html.escape(r['occupancy_status'] or '')}</span><br>{html.escape((r['description'] or '')[:180])}</td><td>{html.escape(r['priority'] or '')}<br><b>{html.escape(r['status'] or '')}</b><br><span class='muted'>{html.escape(r['requested_timeline'] or '')}</span></td><td><details><summary>Review / update</summary><form method='post'><input type='hidden' name='req_id' value='{r['id']}'><select name='status'><option>Submitted</option><option>Under Owner Review</option><option>Needs More Information</option><option>Estimate Needed</option><option>Approved for Scheduling</option><option>Converted to Job</option><option>Closed</option><option>Cancelled</option></select><textarea name='customer_visible_notes' placeholder='Customer-visible update'>{html.escape(r['customer_visible_notes'] or '')}</textarea><textarea name='internal_notes' placeholder='Internal J&R note - customers cannot see this'>{html.escape(r['internal_notes'] or '')}</textarea><button>Update</button></form></details></td></tr>" for r in rows)
    body = f"""<div class='card'><h2>Customer Job Requests - Owner Review</h2><p class='muted'>Customer requests collect contact, property, scheduling, access, safety, photo, and budget notes. Internal notes stay hidden from customer accounts.</p><table><tr><th>ID</th><th>Customer / Contact</th><th>Request Details</th><th>Priority / Status</th><th>Owner Review</th></tr>{row_html or '<tr><td colspan=5>No customer requests yet.</td></tr>'}</table></div>"""
    return layout("Customer Job Requests", body, "applications")
@app.route("/security-audit")
@login_required("audit")
def security_audit_page():
    body = """<div class='card'><h2>Security and Perspective Audit</h2><p>This runs role-based tests for admin, manager, worker, viewer, customer, and non-company accounts. It also checks secure cookie/header settings, internal note separation, and blocked pages.</p><p><a class='btn' href='/security-audit/run'>Run Security Audit</a></p></div>"""
    return layout("Security Audit", body, "health")
@app.route("/security-audit/run")
@login_required("audit")
def security_audit_run():
    import subprocess
    out = EXPORT_DIR / f"JRC_Security_Audit_Run_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    cmd = [sys.executable, str(APP_DIR / "security_perspective_audit.py")]
    try:
        proc = subprocess.run(cmd, cwd=str(BASE_DIR), text=True, capture_output=True, timeout=90)
        out.write_text((proc.stdout or '') + "\n" + (proc.stderr or ''), encoding='utf-8')
        flash(f"Security audit complete. Report: {out.name}", "success" if proc.returncode == 0 else "warning")
    except Exception as exc:
        out.write_text(f"Security audit failed to run: {exc}", encoding='utf-8')
        flash(f"Security audit failed to run. Report: {out.name}", "error")
    return redirect(url_for("health"))
@app.route("/health")
@login_required("audit")
def health():
    rows = db().execute("SELECT * FROM health_events ORDER BY id DESC LIMIT 100").fetchall()
    trs = ''.join(f"<tr><td>{html.escape(r['event_time'])}</td><td><span class='badge {'ok' if r['level']=='OK' else 'yellow' if r['level'] in ['WARN','FIXED'] else 'red'}'>{html.escape(r['level'])}</span></td><td>{html.escape(r['component'])}</td><td>{html.escape(r['message'])}</td></tr>" for r in rows)
    body = f"""<div class="card"><h2>Automatic Troubleshooting</h2>
    <p><a class="btn" href="/health/run">Run Health Check and Auto-Fix Safe Issues</a>
    <a class="btn btn2" href="/backup">Create Backup ZIP</a>
    <a class="btn btn2" href="/admin/troubleshooter">Full Troubleshooter</a>
    <a class="btn btn2" href="/admin">Admin Command Center</a></p>
    <form method="post" action="/admin/run-auto-repair" style="display:inline"><button type="submit">Run Full Auto-Repair</button></form>
    <p class="muted">Full troubleshooter covers launchers, database, shortcuts, host, Densus, pipeline, and health with safe automatic repairs.</p></div><div class="card"><h2>Recent Health Events</h2><table><tr><th>Time</th><th>Level</th><th>Component</th><th>Message</th></tr>{trs}</table></div>"""
    return layout("Troubleshooting", body, "health")
@app.route("/health/run")
@login_required("audit")
def health_run():
    results = run_health_checks()
    log_event("Health", f"Ran health check with {len(results)} results")
    flash("Health check complete.", "success")
    return redirect(url_for("health"))
@app.route("/backup")
@login_required("backup")
def backup():
    BACKUP_DIR.mkdir(exist_ok=True)
    out = BACKUP_DIR / f"J_and_R_Construction_Manager_Backup_{dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.zip"
    from app.dropbox_business import build_backup_zip, sync_backup_to_dropbox
    build_backup_zip(out)
    log_event("Backup", f"Created backup {out.name}")
    try:
        ok, msg, _ = sync_backup_to_dropbox(db(), BASE_DIR)
        if ok:
            flash(f"Backup created and pushed to Dropbox: {msg}", "success")
        else:
            flash(f"Local backup created. Dropbox: {msg}", "warning")
    except Exception as exc:
        flash(f"Local backup created. Dropbox sync skipped: {exc}", "warning")
    return send_file(out, as_attachment=True)

@app.route("/admin/dropbox", methods=["GET", "POST"])
@login_required("view_admin")
def admin_dropbox():
    from app.dropbox_business import (
        discover_dropbox_presets,
        ensure_dropbox_file_source,
        get_dropbox_folder,
        push_business_exports_to_dropbox,
        run_dropbox_live_check,
        set_setting,
        sync_backup_to_dropbox,
    )
    conn = db()
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "save_folder":
            set_setting(conn, "dropbox_folder", request.form.get("dropbox_folder", "").strip())
            ensure_dropbox_file_source(conn)
            flash("Dropbox business folder saved and registered as file source.", "success")
        elif action == "sync_backup":
            ok, msg, _ = sync_backup_to_dropbox(conn, BASE_DIR)
            flash(msg, "success" if ok else "error")
        elif action == "mirror_exports":
            count, msg = push_business_exports_to_dropbox(conn)
            flash(msg, "success")
        elif action == "run_check":
            report = run_dropbox_live_check(conn, BASE_DIR)
            EXPORT_DIR.mkdir(exist_ok=True)
            (EXPORT_DIR / "JRC_Dropbox_Live_Check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            flash("Dropbox live check complete — see exports/JRC_Dropbox_Live_Check.json", "success" if report.get("ok") else "warning")
        return redirect(url_for("admin_dropbox"))
    folder = get_dropbox_folder(conn)
    presets = discover_dropbox_presets()
    preset_opts = "".join(f"<option value='{html.escape(str(p))}'>{html.escape(name)}</option>" for name, p in presets)
    last_backup = get_app_setting("dropbox_last_backup", "Never")
    body = f"""
    <div class='card'><h2>Dropbox Business Backup Source</h2>
    <p class='muted'>Sensitive business files, database backups, and exports are pushed to your local Dropbox-synced folder.
    Dropbox Desktop must be installed and syncing. SQLite is backed up — not live-shared for simultaneous edits.</p>
    <form method='post'><input type='hidden' name='action' value='save_folder'>
    <p><label>Dropbox business folder</label><input name='dropbox_folder' value='{html.escape(folder)}' placeholder='C:\\Users\\...\\Dropbox\\J and R Construction'></p>
    <p><label>Quick pick preset</label><select onchange="document.querySelector('[name=dropbox_folder]').value=this.value">{preset_opts}</select></p>
    <button>Save Folder &amp; Register Source</button></form></div>
    <div class='card'><h2>Actions</h2>
    <form method='post' style='display:inline'><input type='hidden' name='action' value='sync_backup'><button>Push Sensitive Backup to Dropbox</button></form>
    <form method='post' style='display:inline'><input type='hidden' name='action' value='mirror_exports'><button class='btn2'>Mirror Exports to Dropbox</button></form>
    <form method='post' style='display:inline'><input type='hidden' name='action' value='run_check'><button class='btn2'>Run Dropbox Live Check</button></form>
    <p class='muted'>Last Dropbox backup: {html.escape(last_backup)}</p></div>
    <div class='card'><h2>Live Test</h2><ol>
    <li>Confirm Dropbox Desktop is running and green checkmark on your business folder.</li>
    <li>Save folder above → Run Dropbox Live Check → all checks OK.</li>
    <li>Push Sensitive Backup → verify ZIP appears in Dropbox under JRC-Sensitive-Backups.</li>
    <li>Open File Explorer → Refresh Sources → confirm Dropbox files index.</li></ol></div>
    """
    return layout("Dropbox Business", body, "admin")

@app.route("/api/dropbox/status")
@login_required("view_admin")
def api_dropbox_status():
    from app.dropbox_business import run_dropbox_live_check
    return jsonify(run_dropbox_live_check(db(), BASE_DIR))
@app.route("/mobile/ping")
def mobile_ping():
    """Public lightweight phone/LAN connection test."""
    return Response("J&R mobile connection OK - " + now_iso(), mimetype="text/plain")
@app.route("/connect")
def connect_links():
    """Public connection helper page so phones can test host access before login."""
    lan = get_lan_ip()
    port = int(os.environ.get("JRC_PORT", "8765"))
    base = get_app_setting("remote_public_base_url", "").strip() or f"http://{lan}:{port}"
    body = f"""
    <div class='card'><h2>Connection Test</h2>
      <p>This page confirms the shared host is running and reachable from this device.</p>
      <p><b>Server time:</b> {html.escape(now_display())}<br>
      <b>Detected server LAN IP:</b> <code>{html.escape(lan)}</code><br>
      <b>Your IP:</b> <code>{html.escape(client_ip())}</code></p>
      <p><a class='btn' href='/login'>Login</a> <a class='btn btn2' href='/mobile'>Mobile App</a> <a class='btn btn2' href='/register'>Request Account</a> <a class='btn btn2' href='/apply'>Job Application</a></p>
    </div>
    <div class='card'><h2>Share These Links</h2>
      <p><b>Phone/mobile:</b><br><code>{html.escape(base)}/mobile</code></p>
      <p><b>Connection test:</b><br><code>{html.escape(base)}/connect</code></p>
      <p><b>Account request:</b><br><code>{html.escape(base)}/register</code></p>
      <p><b>Job application:</b><br><code>{html.escape(base)}/apply</code></p>
    </div>
    <div class='card'><h2>If Phone Cannot Connect</h2>
      <ol>
        <li>Make sure this computer and phone are on the same Wi-Fi, VPN, or secure tunnel.</li>
        <li>Make sure the shared host is running from the Start Center.</li>
        <li>Run <b>Allow LAN Firewall Access</b> from the program folder or Start Center if Windows firewall blocks the phone.</li>
        <li>For outside locations, set up a secure tunnel/VPN/cloud host and use HTTPS.</li>
      </ol>
    </div>
    """
    return layout("Connection Test and Mobile Links", body, "mobile")
@app.route("/api/connection")
def api_connection():
    port = int(os.environ.get("JRC_PORT", "8765"))
    return jsonify({
        "status": "ok",
        "app": APP_NAME,
        "version": APP_VERSION,
        "time": now_iso(),
        "lan_ip": get_lan_ip(),
        "client_ip": client_ip(),
        "mobile_url": f"http://{get_lan_ip()}:{port}/mobile",
        "connect_url": f"http://{get_lan_ip()}:{port}/connect",
    })
@app.route("/api/local-host-admin")
def api_local_host_admin():
    """Local-only admin status for Start Center monitor (no browser login required on owner PC)."""
    if client_ip() not in ("127.0.0.1", "::1"):
        abort(403)
    cleanup_stale_sessions()
    online_cut = (dt.datetime.now() - dt.timedelta(minutes=15)).isoformat(timespec="seconds")
    rows = db().execute(
        "SELECT session_id, username, role, ip_address, login_time, last_seen, active, revoked FROM online_sessions WHERE active=1 AND revoked=0 AND last_seen >= ? ORDER BY last_seen DESC",
        (online_cut,),
    ).fetchall()
    port = int(os.environ.get("JRC_PORT", "8765"))
    return jsonify({
        "status": "ok",
        "app": APP_NAME,
        "version": APP_VERSION,
        "mode": "public" if PUBLIC_HOST_MODE else "local_lan",
        "port": port,
        "lan_ip": get_lan_ip(),
        "session_timeout_minutes": SESSION_TIMEOUT_MINUTES,
        "active_sessions": len(rows),
        "sessions": [dict(r) for r in rows],
        "cloud_url": get_app_setting("remote_public_base_url", ""),
        "last_boot": get_app_setting("last_server_boot", ""),
        "last_shutdown": get_app_setting("last_server_shutdown", ""),
    })


@app.route("/api/admin/revoke/<sid>", methods=["POST"])
@login_required("view_admin")
def api_revoke_session(sid: str):
    db().execute("UPDATE online_sessions SET revoked=1, active=0, revoke_reason=? WHERE session_id=?", (f"Revoked by {session.get('username')}", sid))
    db().commit()
    log_event("Admin", f"Revoked session {sid}")
    return jsonify({"ok": True, "session_id": sid})


@app.route("/api/health")
def api_health():
    return jsonify({"app": APP_NAME, "version": APP_VERSION, "status": "ok", "time": now_iso(), "lan_ip": get_lan_ip(), "mode": "public" if PUBLIC_HOST_MODE else "local_lan", "session_timeout_minutes": SESSION_TIMEOUT_MINUTES})
def main():
    init_db()
    try:
        from app.server_lifecycle import on_server_startup, register_shutdown_handlers
        from app.host_process import write_host_pid
        on_server_startup()
        register_shutdown_handlers()
        write_host_pid(os.getpid())
    except Exception:
        pass
    host = "0.0.0.0"
    preferred = int(os.environ.get("JRC_PORT", "8765"))
    try:
        from app.runtime_utils import find_launch_port, save_port, is_jrc_server
        if is_jrc_server(preferred):
            port = preferred
        else:
            port = find_launch_port(preferred)
        if port != preferred:
            print(f"Note: port {preferred} is busy or used by another program. Using fallback port {port}.")
            save_port(port, f"Server auto-selected fallback port {port} (preferred {preferred} unavailable).")
        os.environ["JRC_PORT"] = str(port)
    except Exception:
        port = preferred
    print("=" * 70)
    print(APP_NAME, APP_VERSION)
    print(f"Owner: {OWNER} / {BUSINESS_NAME}")
    print(f"Local URL:  http://127.0.0.1:{port}")
    print(f"LAN URL:    http://{get_lan_ip()}:{port}")
    print(f"Mode: {'PUBLIC/HOSTED' if PUBLIC_HOST_MODE else 'LOCAL LAN/VPN'}")
    print("For outside internet use: put this behind HTTPS/VPN/tunnel. Do not expose an unprotected laptop port.")
    print("=" * 70)
    try:
        from waitress import serve

        for try_port in range(port, port + 15):
            try:
                os.environ["JRC_PORT"] = str(try_port)
                if try_port != port:
                    print(f"Retrying on fallback port {try_port}...")
                    try:
                        from app.runtime_utils import save_port
                        save_port(try_port, f"Bind fallback from port {port}.")
                    except Exception:
                        pass
                serve(app, host=host, port=try_port, threads=8)
                return
            except OSError as exc:
                print(f"Could not bind port {try_port}: {exc}")
                continue
        raise SystemExit("No available port found in range.")
    except ImportError:
        app.run(host=host, port=port, debug=False, threaded=True)
@app.route("/v6-final-readiness")
@login_required("audit")
def v6_final_readiness_page():
    body = """
    <div class='card'><h2>v6 Final Readiness</h2>
    <p>This page is for owner/admin verification after install or before cloud deployment. It checks account perspectives, security markers, cloud files, Dropbox/file-source policy, repair tools, and customer/external separation.</p>
    <p><a class='btn' href='/v6-final-readiness/run'>Run v6 Final Readiness</a> <a class='btn btn2' href='/cloud-status'>Cloud Status</a> <a class='btn btn2' href='/setup-status'>Setup Status</a></p>
    <ul><li>Customers and non-company users should only see customer/shared information.</li><li>Admins and managers keep internal office tools.</li><li>Remote users should use Cloud Access or a secure tunnel/VPN, not a sleeping local laptop.</li><li>Dropbox remains file-source/evidence storage and is filtered through role permissions.</li></ul>
    </div>
    """
    return layout("v6 Final Readiness", body, "health")
@app.route("/v6-final-readiness/run")
@login_required("audit")
def v6_final_readiness_run():
    import subprocess
    script = BASE_DIR / "app" / "v6_final_readiness.py"
    try:
        result = subprocess.run([sys.executable, str(script)], cwd=str(BASE_DIR), capture_output=True, text=True, timeout=180)
        out = html.escape((result.stdout or "") + ("\n" + result.stderr if result.stderr else ""))
        level = "success" if result.returncode == 0 else "warning"
        flash("v6 Final Readiness finished. Return code: " + str(result.returncode), level)
    except Exception as exc:
        out = html.escape("Could not run v6 Final Readiness: " + str(exc))
    return layout("v6 Final Readiness Report", f"<div class='card'><h2>v6 Final Readiness Report</h2><pre style='white-space:pre-wrap'>{out}</pre></div>", "health")


@app.route("/customer-request-final-check")
@login_required("audit")
def customer_request_final_check_page():
    body = """<div class='card'><h2>Customer Request Final Check</h2><p>This verifies customer portal request fields, customer-only dashboard behavior, owner-review separation, internal note privacy, and repair-ready request tables.</p><p><a class='btn' href='/customer-request-final-check/run'>Run Customer Request Final Check</a> <a class='btn btn2' href='/customers/requests'>Owner Customer Requests</a></p></div>"""
    return layout("Customer Request Final Check", body, "health")

@app.route("/customer-request-final-check/run")
@login_required("audit")
def customer_request_final_check_run():
    import subprocess
    script = BASE_DIR / "app" / "customer_request_final_check.py"
    try:
        result = subprocess.run([sys.executable, str(script)], cwd=str(BASE_DIR), capture_output=True, text=True, timeout=120)
        out = html.escape((result.stdout or "") + ("\n" + result.stderr if result.stderr else ""))
        flash("Customer Request Final Check finished. Return code: " + str(result.returncode), "success" if result.returncode == 0 else "warning")
    except Exception as exc:
        out = html.escape("Could not run Customer Request Final Check: " + str(exc))
    return layout("Customer Request Final Check Report", f"<div class='card'><h2>Customer Request Final Check Report</h2><pre style='white-space:pre-wrap'>{out}</pre></div>", "health")

@app.route("/live-deployment-readiness")
@login_required("view_admin")
def live_deployment_readiness_page():
    body = """<div class='card'><h2>v6.3 Local Login + Host Repair</h2><p>This tool checks cloud deployment files, role dashboards, security markers, remembered-device policy, customer/external separation, Dropbox/file-source markers, and repair scripts. It writes reports into exports.</p><p><a class='btn' href='/live-deployment-readiness/run'>Run Live Deployment Readiness</a></p></div>"""
    return layout("Live Deployment Readiness", body, "admin")

@app.route("/live-deployment-readiness/run")
@login_required("view_admin")
def live_deployment_readiness_run():
    import subprocess, sys
    script = BASE_DIR / "app" / "live_deployment_readiness.py"
    result = subprocess.run([sys.executable, str(script)], cwd=str(BASE_DIR), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    body = "<div class='card'><h2>Live Deployment Readiness Result</h2><pre>" + html.escape(result.stdout[-8000:]) + "</pre><p>Full report saved in exports.</p></div>"
    return layout("Live Deployment Readiness", body, "admin")

try:
    from app.admin_db_editor import register_admin_db_routes
    register_admin_db_routes(app, layout, login_required, log_event, db, now_iso)
except Exception as _db_route_exc:
    print(f"Warning: Admin database routes not loaded: {_db_route_exc}", file=sys.stderr)

try:
    from app.business_routes import register_business_routes
    register_business_routes(app, layout, login_required, log_event, db, money, now_iso, parse_float)
except Exception as _biz_route_exc:
    print(f"Warning: Business routes not loaded: {_biz_route_exc}", file=sys.stderr)

try:
    from app.densus_routes import register_densus_routes
    register_densus_routes(
        app,
        layout,
        login_required,
        log_event,
        client_ip,
        db,
        now_iso,
        install_dir=BASE_DIR,
    )
except Exception as _densus_route_exc:
    print(f"Warning: Densus admin routes not loaded: {_densus_route_exc}", file=sys.stderr)

try:
    from app.payment_routes import register_payment_routes
    register_payment_routes(app, db, layout, login_required, now_iso)
except Exception as _payment_route_exc:
    print(f"Warning: Payment routes not loaded: {_payment_route_exc}", file=sys.stderr)

try:
    from app.emergency_access import _load_local_secrets
    _load_local_secrets()
    from app.emergency_routes import register_emergency_routes
    register_emergency_routes(app, db, layout, now_iso, client_ip, log_security_event, DEFAULT_ADMIN_USERNAME)
except Exception as _emergency_route_exc:
    print(f"Warning: Emergency routes not loaded: {_emergency_route_exc}", file=sys.stderr)

try:
    from app.live_chat import register_live_chat_routes

    register_live_chat_routes(
        app,
        db_fn=db,
        login_required=login_required,
        layout=layout,
        current_user=current_user,
        is_admin_role=lambda r: normalize_role_for_session(r) == "admin",
        log_event=log_event,
        normalize_role=normalize_role_for_session,
        is_customer_or_external=is_customer_or_external,
    )
except Exception as _live_chat_exc:
    print(f"Warning: Live chat routes not loaded: {_live_chat_exc}", file=sys.stderr)

if __name__ == "__main__":
    main()
