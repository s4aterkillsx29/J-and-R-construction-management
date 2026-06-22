"""
JRC Local Login Gate - v6.6
A no-host, no-Flask quick setup/login gate for the installed PC.
"""
from __future__ import annotations
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
LOG_PATH = LOG_DIR / 'local_login_gate_last.log'
DEFAULT_ADMIN_USERNAME = 'admin'
DEFAULT_ADMIN_PASSWORD = 'admin'
HASH_ITERATIONS_CURRENT = 250000
HASH_ITERATIONS_LEGACY = (200000,)
OWNER = 'Jacob Cosentino'
BG = '#07111f'; PANEL = '#0f172a'; TEXT = '#f8fafc'; MUTED = '#cbd5e1'; ACCENT = '#22c55e'; INFO = '#60a5fa'; BUTTON = '#24324a'

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

def role_key(value) -> str:
    v = (value or '').strip().lower()
    if v == 'admin': return 'admin'
    if v == 'manager': return 'manager'
    if v == 'worker': return 'worker'
    if v == 'viewer' or v == 'user': return 'viewer'
    if v in {'non_company','external','non-company'}: return 'non_company'
    if v == 'customer': return 'customer'
    return v or 'viewer'

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_min_schema():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
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
            log('Created default local first-setup admin/admin because database had no users.')
        elif admin:
            conn.execute("UPDATE users SET role='admin', owner_account=1, active=1 WHERE username=?", (DEFAULT_ADMIN_USERNAME,))
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
    if len(pw or '') < (12 if admin else 8):
        return False, 'Use at least 12 characters for owner/admin passwords.' if admin else 'Use at least 8 characters.'
    if (pw or '').strip().lower() in {'admin','admin123','password','jandr','j&rconstruction','jrconstruction'}:
        return False, 'Choose a stronger password that is not a default/common password.'
    return True, 'OK'

def change_password_dialog(parent, user):
    if tk is None: return False
    current = simpledialog.askstring('Change Password', 'Current password:', show='*', parent=parent)
    if current is None: return False
    if not verify_password(current, user['salt'], user['password_hash']):
        messagebox.showerror('Wrong password', 'Current password did not match.', parent=parent); return False
    new = simpledialog.askstring('Change Password', 'New password (owner/admin: 12+ characters):', show='*', parent=parent)
    if new is None: return False
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
    ensure_min_schema()
    if tk is None:
        print('Tkinter unavailable. Local Login Gate cannot show UI.')
        return 1
    root = tk.Tk(); root.title('JRC Quick Setup Login')
    root.geometry('620x520'); root.minsize(560,480); root.configure(bg=BG)
    try:
        ico = BASE_DIR/'assets'/'j_and_r_manager_icon.ico'
        if ico.exists(): root.iconbitmap(str(ico))
    except Exception: pass
    tk.Label(root, text='J & R Construction Manager', bg=BG, fg=TEXT, font=('Segoe UI',21,'bold')).pack(anchor='w', padx=20, pady=(18,3))
    tk.Label(root, text='Quick Setup Login - no server/host required', bg=BG, fg=INFO, font=('Segoe UI',10,'bold')).pack(anchor='w', padx=20)
    frm = tk.Frame(root, bg=PANEL, padx=18, pady=16); frm.pack(fill='x', padx=20, pady=16)
    tk.Label(frm, text='Username', bg=PANEL, fg=MUTED).grid(row=0,column=0,sticky='w')
    uvar = tk.StringVar(value='admin')
    euser = tk.Entry(frm, textvariable=uvar, font=('Segoe UI',12)); euser.grid(row=1,column=0,sticky='ew', pady=(0,10))
    tk.Label(frm, text='Password', bg=PANEL, fg=MUTED).grid(row=2,column=0,sticky='w')
    pvar = tk.StringVar()
    epass = tk.Entry(frm, textvariable=pvar, show='*', font=('Segoe UI',12)); epass.grid(row=3,column=0,sticky='ew')
    frm.columnconfigure(0, weight=1)
    status = tk.StringVar(value='First setup: use admin / admin. Then change the admin password once. Updates will preserve it.')
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
    def cloud_note():
        messagebox.showinfo('Remote / Cloud Users', 'Customers, workers, and outside users should use the hosted cloud/tunnel URL, not your local installer. Local Login Gate is for this installed PC only.', parent=root)
    def refresh_after_login():
        for child in action_frame.winfo_children(): child.destroy()
        row=logged_user.get('row')
        if not row: return
        role=role_key(row['role'])
        common=[('Change Password',change_pw),('Open Start Center',open_start_center),('Open Logs',lambda: open_path(LOG_DIR)),('Open Exports',lambda: open_path(EXPORT_DIR))]
        if role=='admin':
            actions=[('Open Office',open_office),('Self Setup + Verify',run_self_setup),('Admin Security Check',admin_security)] + common
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
        logged_user['row']=dict(user)
        record_event(username, role, 'OK', 'Verified local login')
        if username==DEFAULT_ADMIN_USERNAME and password==DEFAULT_ADMIN_PASSWORD and is_default_admin_active():
            status.set('First login worked with admin/admin. Change this password now; it will be saved for future installs.')
            messagebox.showwarning('Change default password', 'First login verified. Change admin/admin now before customer, mobile, or cloud access.', parent=root)
            change_password_dialog(root, user)
        else:
            status.set(f"Setup verified: {username} ({role}). Choose the next action below.")
        refresh_after_login()
    tk.Button(btns, text='Login / Continue Setup', command=do_login, bg=ACCENT, fg='#04130a', relief='flat', padx=12, pady=10, font=('Segoe UI',11,'bold')).pack(side='left', fill='x', expand=True, padx=(0,6))
    tk.Button(btns, text='Open Start Center', command=open_start_center, bg=BUTTON, fg=TEXT, relief='flat', padx=12, pady=10, font=('Segoe UI',11,'bold')).pack(side='left', fill='x', expand=True, padx=(6,0))
    epass.bind('<Return>', lambda e: do_login())
    tk.Label(action_frame, text='Log in to show role-based local actions. Customer and external users should use cloud/mobile links provided by J&R.', bg=BG, fg=MUTED, wraplength=560, justify='left').grid(row=0,column=0,sticky='w')
    root.mainloop(); return 0
if __name__ == '__main__':
    log('Local Login Gate opened.'); raise SystemExit(main())
