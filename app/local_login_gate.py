"""
JRC Local Login Gate - v6.6
A no-host, no-Flask quick setup/login gate for the installed PC.
"""
from __future__ import annotations
try:
    from app.win11_compat import enable_win_dpi_awareness
    enable_win_dpi_awareness()
except Exception:
    pass
import hashlib, os, secrets, sqlite3, subprocess, sys, time, webbrowser
from pathlib import Path
try:
    import tkinter as tk
    from tkinter import messagebox, simpledialog
except Exception:
    tk = None

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / 'data'
LOG_DIR = BASE_DIR / 'logs'
EXPORT_DIR = BASE_DIR / 'exports'
DB_PATH = DATA_DIR / 'jr_business.db'
PYTHONW = BASE_DIR / '.venv' / 'Scripts' / 'pythonw.exe'
PYTHON = BASE_DIR / '.venv' / 'Scripts' / 'python.exe'
PY_CMD = str(PYTHONW if PYTHONW.exists() else PYTHON if PYTHON.exists() else sys.executable)
for d in (DATA_DIR, LOG_DIR, EXPORT_DIR):
    d.mkdir(parents=True, exist_ok=True)
try:
    from app.emergency_access import _load_local_secrets
    _load_local_secrets()
except Exception:
    pass
LOG_PATH = LOG_DIR / 'local_login_gate_last.log'
_last_desktop_login: dict | None = None

def get_last_desktop_login() -> dict | None:
    """Return the user dict from the most recent successful desktop blocking/login gate sign-in."""
    return _last_desktop_login


def set_last_desktop_login(user: dict | None) -> None:
    """Remember desktop sign-in for browser SSO bridge."""
    global _last_desktop_login
    _last_desktop_login = dict(user) if user else None
try:
    from app.role_utils import DEFAULT_OWNER_PASSWORD as DEFAULT_ADMIN_PASSWORD
    from app.role_utils import DEFAULT_OWNER_USERNAME as DEFAULT_ADMIN_USERNAME
except Exception:
    DEFAULT_ADMIN_USERNAME = 'admin'
    DEFAULT_ADMIN_PASSWORD = 'ivygrows'
try:
    from app.install_setup_log import get_suggested_admin_username
except Exception:
    def get_suggested_admin_username(base_dir: Path) -> str:
        return DEFAULT_ADMIN_USERNAME
HASH_ITERATIONS_CURRENT = 250000
HASH_ITERATIONS_LEGACY = (200000,)
OWNER = 'Jacob Cosentino'
try:
    from app.ui_theme import BG, PANEL, CARD, BORDER, TEXT, MUTED, ACCENT, INFO, BUTTON, styled_entry, apply_window_icon
    from app.runtime_utils import open_web_dashboard as launch_web_dashboard, open_account_request
except Exception:
    BG = '#0a0f1c'; PANEL = '#111827'; CARD = '#151c2e'; BORDER = '#334155'
    TEXT = '#f5f5f5'; MUTED = '#a3a3a3'; ACCENT = '#84cc16'; INFO = '#a3e635'; BUTTON = '#171717'
    launch_web_dashboard = None
    open_account_request = None
    def styled_entry(parent, **kwargs):
        return tk.Entry(parent, bg='#0f172a', fg=TEXT, insertbackground=TEXT, relief='flat', font=('Segoe UI', 12), **kwargs)
    def apply_window_icon(window, path): pass

def log(msg: str):
    with LOG_PATH.open('a', encoding='utf-8', errors='replace') as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

def now_iso(): return time.strftime('%Y-%m-%dT%H:%M:%S')

def hash_password(password: str, salt: str | None = None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), HASH_ITERATIONS_CURRENT).hex()
    return salt, digest

def verify_password(password: str, salt: str, password_hash: str) -> bool:
    # Current verifier plus legacy compatibility for older JRC desktop builds.
    _, digest = hash_password(password, salt)
    if secrets.compare_digest(digest, password_hash):
        return True
    for iterations in HASH_ITERATIONS_LEGACY:
        legacy = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations).hex()
        if secrets.compare_digest(legacy, password_hash):
            return True
    return False

def password_uses_current_hash(password: str, salt: str, password_hash: str) -> bool:
    _, digest = hash_password(password, salt)
    return secrets.compare_digest(digest, password_hash)

def role_key(value):
    from app.role_utils import normalize_role
    return normalize_role(value)

def db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn

def ensure_min_schema():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from app.db_health import repair_install_database

        ok, msg = repair_install_database(BASE_DIR)
        if not ok:
            log(f"DB repair before login gate: {msg}")
    except Exception as exc:
        log(f"DB repair skipped: {exc}")
    with db() as conn:
        conn.executescript("""
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
            notes TEXT,
            email TEXT,
            recovery_email TEXT,
            phone TEXT,
            title TEXT,
            owner_account INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT);
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
        CREATE TABLE IF NOT EXISTS local_login_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time TEXT,
            username TEXT,
            role TEXT,
            result TEXT,
            message TEXT
        );
        """)
        for stmt in [
            'ALTER TABLE users ADD COLUMN display_name TEXT',
            'ALTER TABLE users ADD COLUMN full_name TEXT',
            'ALTER TABLE users ADD COLUMN email TEXT',
            'ALTER TABLE users ADD COLUMN recovery_email TEXT',
            'ALTER TABLE users ADD COLUMN phone TEXT',
            'ALTER TABLE users ADD COLUMN title TEXT',
            'ALTER TABLE users ADD COLUMN owner_account INTEGER DEFAULT 0',
            'ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 1',
            'ALTER TABLE users ADD COLUMN last_login TEXT',
            'ALTER TABLE users ADD COLUMN notes TEXT',
        ]:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
        total = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        admin = conn.execute('SELECT id FROM users WHERE username=?', (DEFAULT_ADMIN_USERNAME,)).fetchone()
        if total == 0:
            salt, ph = hash_password(DEFAULT_ADMIN_PASSWORD)
            conn.execute("""INSERT INTO users (username, display_name, role, salt, password_hash, active, must_change_password, created_at, notes, email, recovery_email, phone, title, owner_account)
                            VALUES (?, ?, 'admin', ?, ?, 1, 1, ?, ?, ?, ?, ?, ?, 1)""",
                         (DEFAULT_ADMIN_USERNAME, OWNER, salt, ph, now_iso(), 'Default local first-setup admin. Change before sharing access.', 'enragementwow@hotmail.com', 'enragementwow@hotmail.com', '(910) 712-0936', 'Owner / Administrator'))
            conn.execute('INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)', ('owner_setup_complete','0'))
            conn.execute('INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)', ('admin_default_password_changed','0'))
            log(f'Created default local first-setup {DEFAULT_ADMIN_USERNAME} because database had no users.')
        elif admin:
            conn.execute("UPDATE users SET role='admin', owner_account=1, active=1 WHERE username=?", (DEFAULT_ADMIN_USERNAME,))
            conn.execute("UPDATE users SET owner_account=0 WHERE username<>?", (DEFAULT_ADMIN_USERNAME,))
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
        conn.execute('INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)', ('app_version','6.6 Quick Setup Stable Live Edition'))
        conn.commit()

def record_event(username, role, result, message):
    try:
        with db() as conn:
            conn.execute('INSERT INTO local_login_events (event_time,username,role,result,message) VALUES (?,?,?,?,?)', (now_iso(), username, role, result, message))
            conn.execute('INSERT INTO security_events (event_time,level,event_type,username,ip_address,user_agent,message) VALUES (?,?,?,?,?,?,?)', (now_iso(), 'INFO' if result=='OK' else 'WARN', 'local_login_'+result.lower(), username, 'local_pc', 'JRC Local Login Gate', message))
            conn.commit()
    except Exception as e:
        log('Could not record event: '+str(e))

def is_default_admin_active(conn=None):
    own = conn is not None
    conn = conn or db()
    try:
        row = conn.execute('SELECT salt,password_hash,active FROM users WHERE username=?', (DEFAULT_ADMIN_USERNAME,)).fetchone()
        return bool(row and int(row['active'] or 0)==1 and verify_password(DEFAULT_ADMIN_PASSWORD, row['salt'], row['password_hash']))
    finally:
        if not own: conn.close()

def password_quality(pw, admin=True):
    from app.densus_policy import MIN_PASSWORD_LENGTH

    if len(pw or "") < MIN_PASSWORD_LENGTH:
        return False, f"Use at least {MIN_PASSWORD_LENGTH} characters."
    if (pw or '').strip().lower() in {'admin','admin123','password','jandr','j&rconstruction','jrconstruction','ivygrows'}:
        return False, 'Choose a stronger password that is not a default/common password.'
    return True, 'OK'

def change_password_dialog(parent, user):
    if tk is None: return False
    current = simpledialog.askstring('Change Password', 'Current password:', show='*', parent=parent)
    if current is None: return False
    if not verify_password(current, user['salt'], user['password_hash']):
        messagebox.showerror('Wrong password', 'Current password did not match.', parent=parent); return False
    new = simpledialog.askstring('Change Password', 'New password (at least 8 characters):', show='*', parent=parent)
    if new is None: return False
    try:
        from app.first_setup_security import check_password_change_allowed, password_quality_owner
        mastery = simpledialog.askstring('Mastery key', 'Required only if restoring ivygrows default (leave blank otherwise):', show='*', parent=parent) or ''
        ok, msg = check_password_change_allowed(new, mastery)
        if not ok:
            messagebox.showerror('Password blocked', msg, parent=parent); return False
        ok, msg = password_quality_owner(new)
        if not ok:
            messagebox.showerror('Password too weak', msg, parent=parent); return False
    except Exception:
        ok, msg = password_quality(new, admin=user['role']=='admin')
        if not ok:
            messagebox.showerror('Password too weak', msg, parent=parent); return False
    confirm = simpledialog.askstring('Change Password', 'Confirm new password:', show='*', parent=parent)
    if confirm != new:
        messagebox.showerror('Mismatch', 'New passwords did not match.', parent=parent); return False
    salt, ph = hash_password(new)
    with db() as conn:
        conn.execute('UPDATE users SET salt=?, password_hash=?, must_change_password=0 WHERE id=?', (salt, ph, user['id']))
        if user['username'] == DEFAULT_ADMIN_USERNAME:
            conn.execute('INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)', ('owner_setup_complete','1'))
            conn.execute('INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)', ('admin_default_password_changed','1'))
            conn.execute('INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)', ('admin_default_login_disabled_after_change','1'))
            conn.execute('INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)', ('admin_password_changed_at', now_iso()))
        conn.commit()
    record_event(user['username'], user['role'], 'OK', 'Password changed from local login gate.')
    messagebox.showinfo('Password changed', 'Password changed and saved to the business database. Future installs/updates will preserve it.', parent=parent)
    return True

def launch_hidden(args, logname):
    log_path = LOG_DIR / logname
    with log_path.open('a', encoding='utf-8', errors='replace') as logf:
        logf.write('\n--- Launch from Local Login Gate ---\n')
        startupinfo = None; flags = 0
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startupinfo.wShowWindow = 0
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        try:
            return subprocess.Popen(args, cwd=str(BASE_DIR), stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, startupinfo=startupinfo, creationflags=flags), log_path
        except Exception as e:
            logf.write('LAUNCH ERROR: '+str(e)+'\n')
            return None, log_path

def open_path(path: Path):
    try:
        if os.name == 'nt': os.startfile(str(path))
        else: webbrowser.open(str(path))
    except Exception as e:
        log('open_path failed: '+str(e))

def main():
    try:
        from app.desktop_shortcuts import ensure_desktop_shortcuts_async, read_installer_source
        ensure_desktop_shortcuts_async(BASE_DIR, read_installer_source(BASE_DIR))
    except Exception:
        pass
    ensure_min_schema()
    if tk is None:
        print('Tkinter unavailable. Local Login Gate cannot show UI.')
        return 1
    root = tk.Tk(); root.title('JRC Quick Setup Login')
    root.geometry('680x560'); root.minsize(600,500); root.configure(bg=BG)
    apply_window_icon(root, BASE_DIR/'assets'/'j_and_r_manager_icon.ico')
    header = tk.Frame(root, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
    header.pack(fill='x', padx=20, pady=(18, 0))
    tk.Label(header, text='J & R Construction Manager', bg=PANEL, fg=TEXT, font=('Segoe UI',21,'bold')).pack(anchor='w', padx=16, pady=(14,2))
    tk.Label(header, text='Quick setup on this PC — use Web Dashboard for the full glass browser experience', bg=PANEL, fg=INFO, font=('Segoe UI',10,'bold')).pack(anchor='w', padx=16, pady=(0,14))
    frm = tk.Frame(root, bg=CARD, padx=18, pady=16, highlightthickness=1, highlightbackground=BORDER)
    frm.pack(fill='x', padx=20, pady=16)
    tk.Label(frm, text='Username', bg=CARD, fg=MUTED, font=('Segoe UI', 10, 'bold')).grid(row=0,column=0,sticky='w')
    uvar = tk.StringVar(value=get_suggested_admin_username(BASE_DIR))
    euser = styled_entry(frm, textvariable=uvar); euser.grid(row=1,column=0,sticky='ew', ipady=4, pady=(0,10))
    tk.Label(frm, text='Password', bg=CARD, fg=MUTED, font=('Segoe UI', 10, 'bold')).grid(row=2,column=0,sticky='w')
    pvar = tk.StringVar()
    epass = styled_entry(frm, textvariable=pvar, show='*'); epass.grid(row=3,column=0,sticky='ew', ipady=4)
    frm.columnconfigure(0, weight=1)
    status = tk.StringVar(value='Step 1: Log in. Step 2: Change default password if prompted. Customers use web link only — not this screen.')
    tk.Label(root, textvariable=status, bg=BG, fg=MUTED, wraplength=560, justify='left').pack(anchor='w', padx=20, pady=(0,12))
    btns = tk.Frame(root, bg=BG); btns.pack(fill='x', padx=20)
    logged_user = {'row': None}
    action_frame = tk.Frame(root,bg=BG); action_frame.pack(fill='both',expand=True,padx=20,pady=16)

    def open_office():
        proc, lp = launch_hidden([PY_CMD, str(BASE_DIR/'app'/'jr_job_manager.py')], 'desktop_app_last.log')
        status.set('Opening Office app. If it does not appear, check desktop_app_last.log.')
    def open_start_center():
        proc, lp = launch_hidden([PY_CMD, '-m', 'app.start_center'], 'start_center_from_login_gate.log')
        status.set('Opening Start Center.')
    def open_web_dashboard():
        row = logged_user.get('row')
        if launch_web_dashboard:
            if row:
                ok, msg = launch_web_dashboard(
                    sso_user_id=int(row['id']),
                    sso_username=str(row['username']),
                )
            else:
                ok, msg = launch_web_dashboard('/login')
            status.set(msg)
            return
        proc, lp = launch_hidden([PY_CMD, '-m', 'app.network_server'], 'shared_host_from_login_gate.log')
        status.set('Starting web server and opening browser...')
        try:
            from app.runtime_utils import get_saved_port
            port = get_saved_port()
        except Exception:
            port = 8765
        root.after(2500, lambda: webbrowser.open(f'http://127.0.0.1:{port}/login'))
    def run_self_setup():
        proc, lp = launch_hidden([PY_CMD, str(BASE_DIR/'app'/'self_setup_verify.py')], 'self_setup_verify_last.log')
        status.set('Self Setup + Verify running. Check exports/logs for report.')
    def admin_security():
        proc, lp = launch_hidden([PY_CMD, str(BASE_DIR/'app'/'admin_security_final_check.py')], 'admin_security_final_check_last.log')
        status.set('Admin Security Final Check running. Check exports/logs for report.')
    def change_pw():
        row=logged_user.get('row')
        if not row: status.set('Log in first.'); return
        if change_password_dialog(root, row):
            with db() as conn:
                fresh=conn.execute('SELECT * FROM users WHERE id=?', (row['id'],)).fetchone()
            logged_user['row']=dict(fresh)
    def request_account():
        if open_account_request:
            ok, msg = open_account_request()
            status.set(msg or 'Opening account request form in browser...')
            return
        try:
            from app.runtime_utils import get_saved_port
            port = get_saved_port()
        except Exception:
            port = 8765
        webbrowser.open(f'http://127.0.0.1:{port}/register')
        status.set('Opening account request form in browser...')
    def cloud_note():
        messagebox.showinfo('Remote / Cloud Users', 'Customers, workers, and outside users should use the hosted cloud/tunnel URL, not your local installer. Local Login Gate is for this installed PC only.', parent=root)
    def emergency_mastery():
        key = simpledialog.askstring('Emergency Owner Access', 'Enter owner mastery key:', show='*', parent=root)
        if not key:
            return
        try:
            from app.emergency_access import verify_mastery_key, grant_emergency_admin_access
            if not verify_mastery_key(key):
                record_event('admin', '', 'FAILED', 'Invalid mastery key at local login gate')
                status.set('Invalid mastery key.')
                messagebox.showerror('Denied', 'Invalid mastery key.', parent=root)
                return
            with db() as conn:
                ok, msg = grant_emergency_admin_access(conn, 'local_pc', 'JRC Local Login Gate emergency')
                admin = conn.execute(
                    "SELECT * FROM users WHERE LOWER(role)='admin' AND active=1 ORDER BY owner_account DESC, id LIMIT 1"
                ).fetchone()
            try:
                from app.install_setup_log import log_event
                log_event(BASE_DIR, 'EmergencyAccess', msg, level='INFO' if ok else 'ERROR', step='emergency_access')
            except Exception:
                pass
            if not ok or not admin:
                status.set(msg)
                messagebox.showerror('Emergency access', msg, parent=root)
                return
            logged_user['row'] = dict(admin)
            record_event('admin', 'admin', 'OK', 'Emergency mastery key used — admin unlocked locally')
            status.set('Emergency admin access granted. Admin account unlocked.')
            messagebox.showwarning('Emergency access', 'Admin unlocked. Use your admin password or open Web Dashboard.', parent=root)
            refresh_after_login()
        except Exception as e:
            log('Emergency mastery error: ' + str(e))
            status.set('Emergency access error. Check logs.')
    def refresh_after_login():
        for child in action_frame.winfo_children(): child.destroy()
        row=logged_user.get('row')
        if not row: return
        role=role_key(row['role'])
        common=[('Change Password',change_pw),('Open Start Center',open_start_center),('Open Logs',lambda: open_path(LOG_DIR)),('Open Exports',lambda: open_path(EXPORT_DIR))]
        if role=='admin':
            actions=[('Open Web Dashboard',open_web_dashboard),('Open Office',open_office),('Self Setup + Verify',run_self_setup),('Admin Security Check',admin_security),('Emergency Owner Access',emergency_mastery)] + common
        elif role=='manager':
            actions=[('Open Office',open_office),('Open Start Center',open_start_center),('Open Exports',lambda: open_path(EXPORT_DIR))]
        else:
            actions=[('Cloud/Mobile Access Info',cloud_note),('Open Start Center',open_start_center),('Change Password',change_pw)]
        for i,(label,cmd) in enumerate(actions):
            tk.Button(action_frame, text=label, command=cmd, bg=BUTTON, fg=TEXT, relief='flat', padx=10, pady=8, font=('Segoe UI',10,'bold')).grid(row=i//2,column=i%2,sticky='ew',padx=5,pady=5)
        action_frame.columnconfigure(0,weight=1); action_frame.columnconfigure(1,weight=1)
    def do_login():
        username=uvar.get().strip(); password=pvar.get()
        with db() as conn:
            user=conn.execute('SELECT * FROM users WHERE username=? AND active=1', (username,)).fetchone()
        if not user or not verify_password(password, user['salt'], user['password_hash']):
            record_event(username, '', 'FAILED', 'Invalid local login')
            status.set('Login failed. Check username/password or use owner recovery if locked out.')
            return
        role = role_key(user['role'])
        # Migrate legacy 200k PBKDF2 hashes to the current verifier on any successful login.
        with db() as conn:
            if not password_uses_current_hash(password, user['salt'], user['password_hash']):
                nsalt, nph = hash_password(password)
                conn.execute('UPDATE users SET salt=?, password_hash=? WHERE id=?', (nsalt, nph, user['id']))
                user = conn.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
                record_event(username, role, 'OK', 'Migrated legacy password hash to current settings')
            if role != user['role']:
                conn.execute('UPDATE users SET role=? WHERE id=?', (role, user['id']))
                user = conn.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
            conn.execute('UPDATE users SET last_login=? WHERE id=?', (now_iso(), user['id'])); conn.commit()
            try:
                from app.master_owner import register_master_owner_device
                register_master_owner_device(username, conn)
            except Exception:
                pass
        logged_user['row']=dict(user)
        global _last_desktop_login
        _last_desktop_login = dict(user)
        record_event(username, role, 'OK', 'Verified local login')
        try:
            from app.install_setup_log import log_event, mark_step, write_setup_report
            log_event(BASE_DIR, 'LoginGate', f'User {username} logged in role={role}')
            mark_step(BASE_DIR, 'post_login', 'ok', f'Logged in as {username}')
            write_setup_report(BASE_DIR)
        except Exception:
            pass
        try:
            from app.post_verification_update import spawn_post_verification_update
            ok, pmsg = spawn_post_verification_update(BASE_DIR, dict(user))
            if ok:
                status.set(f'Logged in as {username}. {pmsg}')
        except Exception:
            pass
        if username == DEFAULT_ADMIN_USERNAME and password == DEFAULT_ADMIN_PASSWORD and is_default_admin_active():
            status.set(f'First login worked with default password. Change this password now; it will be saved for future installs.')
            messagebox.showwarning('Change default password', f'First login verified. Change the default {DEFAULT_ADMIN_USERNAME} password now before customer, mobile, or cloud access.', parent=root)
            change_password_dialog(root, user)
        else:
            status.set(f"Setup verified: {username} ({role}). Choose the next action below.")
        refresh_after_login()
    tk.Button(btns, text='Request Account', command=request_account, bg='#1e293b', fg=INFO, relief='flat', padx=8, pady=10, font=('Segoe UI',10,'bold')).pack(side='left', fill='x', expand=True, padx=(0,6))
    tk.Button(btns, text='Open Web UI (Glass Dashboard)', command=open_web_dashboard, bg=INFO, fg='#0c1222', relief='flat', padx=12, pady=10, font=('Segoe UI',11,'bold')).pack(side='left', fill='x', expand=True, padx=(0,6))
    tk.Button(btns, text='Login / Continue Setup', command=do_login, bg=ACCENT, fg='#04130a', relief='flat', padx=12, pady=10, font=('Segoe UI',11,'bold')).pack(side='left', fill='x', expand=True, padx=(0,6))
    tk.Button(btns, text='Start Center', command=open_start_center, bg=BUTTON, fg=TEXT, relief='flat', padx=12, pady=10, font=('Segoe UI',11,'bold')).pack(side='left', fill='x', expand=True, padx=(6,0))
    tk.Button(btns, text='Emergency Owner', command=emergency_mastery, bg='#3f1d1d', fg='#fca5a5', relief='flat', padx=8, pady=10, font=('Segoe UI',10,'bold')).pack(side='left', fill='x', expand=True, padx=(6,0))
    epass.bind('<Return>', lambda e: do_login())
    tk.Label(action_frame, text='Log in to show role-based local actions. Customer and external users should use cloud/mobile links provided by J&R.', bg=BG, fg=MUTED, wraplength=560, justify='left').grid(row=0,column=0,sticky='w')
    root.mainloop(); return 0


def require_blocking_login(context: str = "JRC Manager") -> bool:
    """Require sign-in before desktop tools run. Returns False if user cancels."""
    try:
        from app.desktop_session import get_active_desktop_session

        sess = get_active_desktop_session(BASE_DIR)
        if sess and sess.get("user"):
            set_last_desktop_login(dict(sess["user"]))
            return True
    except Exception as exc:
        log(f"Session resume failed: {exc}")
    if tk is None:
        print(f"{context}: Tkinter unavailable — login gate skipped.")
        return True
    try:
        ensure_min_schema()
    except Exception as exc:
        log(f"Login gate schema/DB error: {exc}")
        try:
            from app.db_health import repair_install_database

            ok, msg = repair_install_database(BASE_DIR)
            if not ok:
                messagebox.showerror(
                    "Login Gate Failed",
                    f"Database error — login could not start.\n\n{exc}\n\nRepair: {msg[:400]}",
                )
                return False
            ensure_min_schema()
        except Exception as exc2:
            messagebox.showerror("Login Gate Failed", f"Database malformed or locked.\n\n{exc2}")
            return False
    result = {"ok": False}

    root = tk.Tk()
    root.withdraw()
    win = tk.Toplevel(root)
    win.title(f"Sign In Required — {context}")
    win.geometry("480x360")
    win.minsize(420, 320)
    win.configure(bg=BG)
    win.grab_set()
    apply_window_icon(win, BASE_DIR / "assets" / "j_and_r_manager_icon.ico")
    tk.Label(win, text="J & R Construction Manager", bg=BG, fg=TEXT, font=("Segoe UI", 16, "bold")).pack(pady=(16, 4))
    tk.Label(win, text=f"Sign in to open {context}. Every user including admin must verify on this PC.", bg=BG, fg=MUTED, wraplength=420).pack(pady=(0, 12))
    frm = tk.Frame(win, bg=CARD, padx=16, pady=12)
    frm.pack(fill="x", padx=20)
    uvar = tk.StringVar(value=get_suggested_admin_username(BASE_DIR))
    pvar = tk.StringVar()
    tk.Label(frm, text="Username", bg=CARD, fg=MUTED).pack(anchor="w")
    styled_entry(frm, textvariable=uvar).pack(fill="x", pady=(0, 8))
    tk.Label(frm, text="Password", bg=CARD, fg=MUTED).pack(anchor="w")
    epass = styled_entry(frm, show="*", textvariable=pvar)
    epass.pack(fill="x")
    status = tk.StringVar(value="PC-rooted security: login required before program use.")

    def request_account_blocking():
        if open_account_request:
            open_account_request()
            status.set("Account request form opened in browser — admin will review.")
            return
        try:
            from app.runtime_utils import get_saved_port
            port = get_saved_port()
        except Exception:
            port = 8765
        webbrowser.open(f"http://127.0.0.1:{port}/register")
        status.set("Account request form opened in browser — admin will review.")

    def do_login(_event=None):
        username = uvar.get().strip()
        password = pvar.get()
        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
        if not user or not verify_password(password, user["salt"], user["password_hash"]):
            record_event(username, "", "FAILED", f"Blocking login denied for {context}")
            status.set("Login failed. Check username and password.")
            return
        record_event(username, role_key(user["role"]), "OK", f"Blocking login OK for {context}")
        global _last_desktop_login
        _last_desktop_login = dict(user)
        result["ok"] = True
        try:
            from app.desktop_session import create_desktop_session

            create_desktop_session(dict(user), BASE_DIR, source=f"blocking_{context}")
        except Exception:
            pass
        win.destroy()

    def cancel():
        result["ok"] = False
        win.destroy()

    tk.Label(win, textvariable=status, bg=BG, fg=MUTED, wraplength=420).pack(pady=8)
    req = tk.Frame(win, bg=BG)
    req.pack(fill="x", padx=20)
    tk.Label(
        req,
        text="No account? Request access — owner/admin reviews and emails you when approved.",
        bg=BG,
        fg=MUTED,
        wraplength=420,
        justify="left",
    ).pack(anchor="w", pady=(0, 6))
    tk.Button(
        req,
        text="Request Account (Admin Review)",
        command=request_account_blocking,
        bg="#1e293b",
        fg=INFO,
        relief="flat",
        padx=10,
        pady=6,
        font=("Segoe UI", 10, "bold"),
    ).pack(anchor="w", pady=(0, 4))
    btns = tk.Frame(win, bg=BG)
    btns.pack(fill="x", padx=20, pady=8)
    tk.Button(btns, text="Sign In", command=do_login, bg=ACCENT, fg="#04130a", relief="flat", padx=12, pady=8).pack(side="left", expand=True, fill="x", padx=(0, 6))
    tk.Button(btns, text="Cancel", command=cancel, bg=BUTTON, fg=TEXT, relief="flat", padx=12, pady=8).pack(side="left", expand=True, fill="x")
    epass.bind("<Return>", do_login)
    win.protocol("WM_DELETE_WINDOW", cancel)
    root.wait_window(win)
    try:
        root.destroy()
    except Exception:
        pass
    return bool(result["ok"])


if __name__ == '__main__':
    log('Local Login Gate opened.'); raise SystemExit(main())
