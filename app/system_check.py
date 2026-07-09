"""J and R Construction Manager local system check and safe repair tool."""
from __future__ import annotations
import os, sys, sqlite3, json, zipfile, datetime as dt, traceback
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BASE_DIR / "app"
DATA_DIR = BASE_DIR / "data"
DB = DATA_DIR / "jr_business.db"
REQUIRED_DIRS = ["data", "exports", "evidence", "backups", "chatgpt_imports", "logs", "business_standards"]
REQUIRED_FILES = [APP_DIR/"jr_job_manager.py", APP_DIR/"network_server.py", APP_DIR/"start_center.py"]
VERSION_FILE = BASE_DIR / "VERSION.txt"
REPORT_DIR = BASE_DIR / "exports"


def now(): return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def add(results, level, component, message):
    results.append((level, component, message))


def safe_db_log(level, component, message):
    try:
        if not DB.exists(): return
        with sqlite3.connect(DB) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS health_events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_time TEXT, level TEXT, component TEXT, message TEXT, fixed INTEGER DEFAULT 0)")
            conn.execute("INSERT INTO health_events (event_time, level, component, message, fixed) VALUES (?,?,?,?,?)", (now(), level, component, message, 1 if level == "FIXED" else 0))
    except Exception:
        pass


def check_platform(results):
    try:
        from app.win11_compat import enable_win_dpi_awareness, is_windows_11_or_newer, platform_summary
        enable_win_dpi_awareness()
        add(results, "OK", "Windows", platform_summary())
        if is_windows_11_or_newer():
            add(results, "OK", "Windows 11", "Windows 11 or newer detected — DPI-aware UI enabled.")
        else:
            add(results, "INFO", "Windows", "Running on Windows 10 or earlier — compatibility mode active.")
    except Exception as exc:
        add(results, "WARN", "Windows", f"Platform check skipped: {exc}")


def check_runtime_env(results):
    venv_py = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        add(results, "OK", "Runtime", f"Virtual environment ready: {venv_py}")
    else:
        add(results, "ERROR", "Runtime", "Python virtual environment missing. Run setup_runtime_env.bat or reinstall.")
    try:
        import flask  # noqa: F401
        add(results, "OK", "Runtime", "Flask is installed for shared host and web dashboard.")
    except Exception:
        add(results, "ERROR", "Runtime", "Flask missing. Run setup_runtime_env.bat from the install folder.")


def repair_schema(results):
    """Safe automatic repair for tables/columns used by shared sessions, account requests, payroll, invoices, and job costing."""
    try:
        from app.schema_migrations import ensure_all_shared_schemas
        if DB.exists():
            with sqlite3.connect(DB) as conn:
                ensure_all_shared_schemas(conn)
            add(results, "FIXED", "Schema Migration", "Unified file_sources and shared schema columns verified.")
    except Exception as exc:
        add(results, "WARN", "Schema Migration", f"Could not run unified schema migration: {exc}")
    if not DB.exists():
        return
    try:
        with sqlite3.connect(DB) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS file_sources (id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT, source_type TEXT, folder_path TEXT UNIQUE, active INTEGER DEFAULT 1, created_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS file_index (id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER, file_path TEXT UNIQUE, file_name TEXT, extension TEXT, size INTEGER, modified_at TEXT, discovered_at TEXT, keywords TEXT, analysis TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS business_standards (id INTEGER PRIMARY KEY AUTOINCREMENT, standard_key TEXT UNIQUE, category TEXT, title TEXT, standard_value TEXT, editable INTEGER DEFAULT 1, updated_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS security_events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_time TEXT, level TEXT, event_type TEXT, username TEXT, ip_address TEXT, user_agent TEXT, message TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS account_request_settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS account_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, requested_username TEXT UNIQUE NOT NULL, display_name TEXT, email TEXT, recovery_email TEXT, phone TEXT, address TEXT, worker_type TEXT, skills TEXT, emergency_contact TEXT, preferred_rate REAL DEFAULT 0, requested_role TEXT DEFAULT 'worker', salt TEXT, password_hash TEXT, status TEXT DEFAULT 'Pending', request_ip TEXT, request_user_agent TEXT, admin_notes TEXT, created_at TEXT, reviewed_at TEXT, reviewed_by TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS online_sessions (session_id TEXT PRIMARY KEY, user_id INTEGER, username TEXT, role TEXT, ip_address TEXT, user_agent TEXT, trusted_device_id TEXT, client_device_fingerprint TEXT, client_device_label TEXT, device_trust_status TEXT, login_time TEXT, last_seen TEXT, active INTEGER DEFAULT 1, revoked INTEGER DEFAULT 0, revoke_reason TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS known_devices (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, device_fingerprint TEXT UNIQUE, device_label TEXT, device_kind TEXT DEFAULT 'browser', first_ip TEXT, last_ip TEXT, first_user_agent TEXT, last_user_agent TEXT, first_seen TEXT, last_seen TEXT, trust_status TEXT DEFAULT 'observed', approved_by TEXT, approved_at TEXT, blocked_by TEXT, blocked_at TEXT, notes TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS owner_recovery_events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_time TEXT, action TEXT, username TEXT, ip_address TEXT, user_agent TEXT, trusted_admin_device_id TEXT, result TEXT, notes TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS permissions_override (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, permission TEXT, allowed INTEGER DEFAULT 1, created_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS payroll_periods (id INTEGER PRIMARY KEY AUTOINCREMENT, period_name TEXT, start_date TEXT, end_date TEXT, status TEXT DEFAULT 'Open', total_worker_pay REAL DEFAULT 0, total_cost_fees REAL DEFAULT 0, total_hours REAL DEFAULT 0, created_at TEXT, closed_at TEXT, notes TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS job_cost_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER, snapshot_time TEXT, revenue REAL DEFAULT 0, deposits REAL DEFAULT 0, paid REAL DEFAULT 0, material_expenses REAL DEFAULT 0, worker_pay REAL DEFAULT 0, payroll_cost_fees REAL DEFAULT 0, owner_labor_value REAL DEFAULT 0, total_known_cost REAL DEFAULT 0, estimated_profit REAL DEFAULT 0, notes TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS invoices (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER, invoice_number TEXT, invoice_type TEXT DEFAULT 'Invoice', issue_date TEXT, due_date TEXT, status TEXT DEFAULT 'Draft', subtotal REAL DEFAULT 0, deposit_due REAL DEFAULT 0, paid_amount REAL DEFAULT 0, balance_due REAL DEFAULT 0, payment_terms TEXT, notes TEXT, created_at TEXT, updated_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS invoice_payments (id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER, job_id INTEGER, payment_date TEXT, amount REAL DEFAULT 0, method TEXT, reference TEXT, notes TEXT, created_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS bookkeeping_ledgers (id INTEGER PRIMARY KEY AUTOINCREMENT, entry_date TEXT, entry_type TEXT, category TEXT, job_id INTEGER, source_table TEXT, source_id INTEGER, description TEXT, debit REAL DEFAULT 0, credit REAL DEFAULT 0, status TEXT DEFAULT 'Open', receipt_status TEXT, created_at TEXT, updated_at TEXT, notes TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS bookkeeping_rules (id INTEGER PRIMARY KEY AUTOINCREMENT, rule_name TEXT, match_text TEXT, category TEXT, entry_type TEXT, active INTEGER DEFAULT 1, notes TEXT, created_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS bookkeeping_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, run_time TEXT, run_type TEXT, total_income REAL DEFAULT 0, total_expenses REAL DEFAULT 0, total_worker_pay REAL DEFAULT 0, total_receivables REAL DEFAULT 0, unmatched_receipts INTEGER DEFAULT 0, missing_receipts INTEGER DEFAULT 0, duplicate_file_names INTEGER DEFAULT 0, open_jobs INTEGER DEFAULT 0, notes TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS filekeeping_reviews (id INTEGER PRIMARY KEY AUTOINCREMENT, run_time TEXT, source_count INTEGER DEFAULT 0, indexed_files INTEGER DEFAULT 0, duplicate_file_names INTEGER DEFAULT 0, receipt_like_files INTEGER DEFAULT 0, missing_receipts INTEGER DEFAULT 0, inactive_sources INTEGER DEFAULT 0, missing_source_paths INTEGER DEFAULT 0, notes TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS bookkeeping_alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, alert_type TEXT, severity TEXT, title TEXT, message TEXT, related_table TEXT, related_id INTEGER, resolved INTEGER DEFAULT 0, resolved_at TEXT, resolved_by TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS job_applications (id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT DEFAULT 'Pending Owner Review', created_at TEXT, updated_at TEXT, reviewed_at TEXT, reviewed_by TEXT, owner_notes TEXT, full_name TEXT, requested_username TEXT, phone TEXT, email TEXT, recovery_email TEXT, address TEXT, date_available TEXT, desired_position TEXT, worker_type TEXT, preferred_rate REAL DEFAULT 0, rate_type TEXT, availability TEXT, transportation TEXT, drivers_license_status TEXT, own_tools TEXT, skills TEXT, experience_years TEXT, work_history TEXT, references_text TEXT, emergency_contact_name TEXT, emergency_contact_phone TEXT, insurance_full_legal_name TEXT, insurance_address TEXT, insurance_phone TEXT, insurance_email TEXT, insurance_date_of_birth TEXT, insurance_driver_license_state TEXT, insurance_driver_license_number TEXT, insurance_vehicle_use TEXT, insurance_employment_classification TEXT, insurance_requested_coverage TEXT, w9_status TEXT, id_document_status TEXT, insurance_notes TEXT, request_ip TEXT, request_user_agent TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS application_events (id INTEGER PRIMARY KEY AUTOINCREMENT, application_id INTEGER, event_time TEXT, event_type TEXT, username TEXT, message TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS customer_user_profiles (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE, username TEXT, customer_id INTEGER, display_name TEXT, email TEXT, phone TEXT, address TEXT, portal_status TEXT DEFAULT 'Active', created_at TEXT, updated_at TEXT, notes TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS customer_job_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_user_id INTEGER, customer_id INTEGER, created_by_username TEXT, status TEXT DEFAULT 'Submitted', priority TEXT DEFAULT 'Normal', request_title TEXT, service_type TEXT, property_address TEXT, requested_timeline TEXT, access_notes TEXT, description TEXT, photos_notes TEXT, customer_visible_notes TEXT, internal_notes TEXT, submitted_at TEXT, updated_at TEXT, reviewed_at TEXT, reviewed_by TEXT, converted_job_id INTEGER, request_ip TEXT, request_user_agent TEXT, contact_name TEXT, contact_phone TEXT, contact_email TEXT, best_contact_method TEXT, property_type TEXT, occupancy_status TEXT, tenant_name TEXT, tenant_phone TEXT, appointment_window TEXT, safety_notes TEXT, pets_notes TEXT, budget_range TEXT, request_reason TEXT, customer_acknowledged INTEGER DEFAULT 0)")
            existing = {r[1] for r in conn.execute("PRAGMA table_info(customer_job_requests)").fetchall()}
            for name, ctype in {
                "contact_name":"TEXT", "contact_phone":"TEXT", "contact_email":"TEXT", "best_contact_method":"TEXT",
                "property_type":"TEXT", "occupancy_status":"TEXT", "tenant_name":"TEXT", "tenant_phone":"TEXT",
                "appointment_window":"TEXT", "safety_notes":"TEXT", "pets_notes":"TEXT", "budget_range":"TEXT",
                "request_reason":"TEXT", "customer_acknowledged":"INTEGER DEFAULT 0"
            }.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE customer_job_requests ADD COLUMN {name} {ctype}")
            conn.execute("CREATE TABLE IF NOT EXISTS customer_request_events (id INTEGER PRIMARY KEY AUTOINCREMENT, request_id INTEGER, event_time TEXT, event_type TEXT, username TEXT, message TEXT)")
            # Add columns safely for older installs.
            for table, coldef in [
                ('users','email TEXT'), ('users','recovery_email TEXT'), ('users','phone TEXT'), ('users','title TEXT'),
                ('users','owner_account INTEGER DEFAULT 0'), ('users','last_ip_address TEXT'), ('users','last_user_agent TEXT'),
                ('worker_payments','hours REAL DEFAULT 0'), ('worker_payments','rate REAL DEFAULT 0'), ('worker_payments','cost_fee REAL DEFAULT 0'),
                ('worker_payments','approved_by TEXT'), ('worker_payments','approved_at TEXT'), ('worker_payments','paid_at TEXT'),
                ('worker_payments','payroll_period_id INTEGER'), ('worker_payments',"source TEXT DEFAULT 'manual'"), ('online_sessions','client_device_fingerprint TEXT'), ('online_sessions','client_device_label TEXT'), ('online_sessions','device_trust_status TEXT')
            ]:
                try: conn.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")
                except Exception: pass
            conn.execute("INSERT OR REPLACE INTO account_request_settings (key,value) VALUES ('public_account_requests','enabled')")
            conn.execute("INSERT OR REPLACE INTO account_request_settings (key,value) VALUES ('approval_required','true')")
            conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES ('public_account_requests','enabled')")
            conn.commit()
            add(results,'FIXED','Auto Repair','Verified/repaired account, permission, session, remembered-device, owner-recovery, payroll, invoice, job-cost, bookkeeping, filekeeping review, alert, and security-event tables.')
    except Exception as exc:
        add(results,'ERROR','Auto Repair',f'Could not repair shared-account/customer-portal schema: {exc}')


def run():
    results=[]
    add(results,"INFO","Version", VERSION_FILE.read_text(encoding='utf-8').strip() if VERSION_FILE.exists() else "Version file missing")
    check_platform(results)
    check_runtime_env(results)
    repair_schema(results)
    try:
        from app.data_pipeline import verify_pipelines, ensure_master_storage_layout
        ensure_master_storage_layout()
        for level, comp, msg in verify_pipelines():
            add(results, level if level in ("OK", "ERROR", "WARN", "INFO", "FIXED") else "INFO", comp, msg)
    except Exception as exc:
        add(results, "WARN", "Data Pipeline", str(exc))
    for d in REQUIRED_DIRS:
        p=BASE_DIR/d
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            add(results,"FIXED","Folder",f"Created missing folder: {d}")
        else:
            add(results,"OK","Folder",f"Found folder: {d}")
    for f in REQUIRED_FILES:
        add(results,"OK" if f.exists() else "ERROR","Program File",f"{'Found' if f.exists() else 'Missing'}: {f.relative_to(BASE_DIR)}")
    # syntax compile
    import py_compile
    for f in REQUIRED_FILES:
        if f.exists():
            try:
                py_compile.compile(str(f), doraise=True)
                add(results,"OK","Python Compile",f"Compiled: {f.name}")
            except Exception as exc:
                add(results,"ERROR","Python Compile",f"Failed {f.name}: {exc}")
    # db checks
    if DB.exists():
        try:
            from app.db_health import ensure_database_healthy, sqlite_session

            ok, msg = ensure_database_healthy(DB, log_dir=BASE_DIR / "logs")
            add(results, "OK" if ok else "WARN", "Database Health", msg)
            with sqlite_session(DB) as conn:
                integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                add(results, "OK" if integrity == "ok" else "ERROR", "Database", f"Integrity check: {integrity}")
                # ensure important tables exist
                tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                for t in ["users","jobs","expenses","file_index","file_sources","online_sessions","account_requests","permissions_override","security_events","health_events","business_standards","workers","worker_payments","payroll_periods","job_cost_snapshots","invoices","invoice_payments","known_devices","owner_recovery_events","bookkeeping_ledgers","bookkeeping_rules","bookkeeping_runs","filekeeping_reviews","bookkeeping_alerts","job_applications","application_events","customer_user_profiles","customer_job_requests","customer_request_events"]:
                    add(results,"OK" if t in tables else "WARN","Database Table",f"{t}: {'present' if t in tables else 'missing; app will create on next server start'}")
                # default admin warning: only warn when admin still needs first password change.
                row=conn.execute("SELECT username, must_change_password FROM users WHERE username='admin' LIMIT 1").fetchone() if 'users' in tables else None
                if row and int(row[1] or 0) == 1:
                    add(results,"WARN","Security","Default/temporary admin password still needs to be changed before sharing access.")
                elif row:
                    add(results,"OK","Security","Admin account exists and is not marked for default password change.")
                if 'account_requests' in tables:
                    pending=conn.execute("SELECT COUNT(*) FROM account_requests WHERE status='Pending'").fetchone()[0]
                    add(results,"OK" if pending==0 else "WARN","Account Requests",f"{pending} pending request(s) waiting for admin review.")
                if 'online_sessions' in tables:
                    cutoff=(dt.datetime.now()-dt.timedelta(hours=4)).isoformat(timespec='seconds')
                    stale=conn.execute("UPDATE online_sessions SET active=0, revoke_reason='System Check cleanup: stale session' WHERE active=1 AND last_seen < ?", (cutoff,)).rowcount
                    if stale: add(results,"FIXED","Sessions",f"Closed {stale} stale online session(s).")
        except Exception as exc:
            add(results,"ERROR","Database",f"Database check failed: {exc}")
    else:
        add(results,"WARN","Database","Database missing. Run installer or open app to initialize records.")
    # backup quick test
    try:
        bdir=BASE_DIR/"backups"; bdir.mkdir(exist_ok=True)
        marker=bdir/("system_check_marker_"+dt.datetime.now().strftime('%Y%m%d_%H%M%S')+".txt")
        marker.write_text("System check marker created "+now(), encoding='utf-8')
        add(results,"OK","Backup Folder","Backup folder is writable.")
        try: marker.unlink()
        except Exception: pass
    except Exception as exc:
        add(results,"ERROR","Backup Folder",f"Backup folder is not writable: {exc}")
    # write report
    REPORT_DIR.mkdir(exist_ok=True)
    report=REPORT_DIR/("JRC_System_Check_Report_"+dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')+".txt")
    lines=["J and R Construction Manager - System Check / Auto Repair v4.1", "Generated: "+now(), "Install folder: "+str(BASE_DIR), "", "Results:"]
    for level, comp, msg in results:
        lines.append(f"[{level}] {comp}: {msg}")
        safe_db_log(level, comp, msg)
    errors=[r for r in results if r[0]=='ERROR']
    warns=[r for r in results if r[0]=='WARN']
    lines.append("")
    lines.append(f"Summary: {len(errors)} error(s), {len(warns)} warning(s), {len([r for r in results if r[0]=='FIXED'])} safe fix(es).")
    report.write_text("\n".join(lines), encoding='utf-8')
    print("\n".join(lines))
    print("\nReport saved to:", report)
    return 1 if errors else 0

if __name__ == '__main__':
    try:
        raise SystemExit(run())
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
