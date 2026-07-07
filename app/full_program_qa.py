"""
J & R Construction Manager - Full Program QA / Business Readiness Check
This is an offline static and database QA tool. It does not require Flask or internet.
It checks the installed package structure, key code features, database/schema readiness,
security patterns, mobile/shared-session routes, bookkeeping/payroll areas, and installer files.
"""
from __future__ import annotations
import ast
import datetime as dt
import os
import re
import sqlite3
import sys
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BASE_DIR / 'app'
DATA_DIR = BASE_DIR / 'data'
EXPORT_DIR = BASE_DIR / 'exports'
DB_PATH = DATA_DIR / 'jr_business.db'

REQUIRED_FILES = [
    '!!! START INSTALL HERE.vbs',
    '!!! START INSTALL HERE.bat',
    '00_READ_ME_FIRST_INSTALL.txt',
    'INSTALL_J_AND_R_MANAGER.vbs',
    'install_jr_job_manager_ui.ps1',
    'app/start_center.py',
    'app/jr_job_manager.py',
    'app/network_server.py',
    'app/system_check.py',
    'app/full_program_qa.py',
    'assets/j_and_r_manager_icon.ico',
    'VERSION.txt',
]

REQUIRED_DIRS = ['data','exports','evidence','backups','chatgpt_imports','business_standards','logs']

REQUIRED_ROUTES = [
    '/login','/register','/apply','/applications','/mobile','/mobile/setup','/mobile/jobs','/mobile/files',
    '/connect','/mobile/ping','/api/connection','/api/health','/admin','/admin/devices',
    '/payroll','/job-costs','/bookkeeping','/filekeeping','/health','/backup','/remote-mobile'
]

REQUIRED_TABLES = [
    'users','jobs','expenses','file_index','file_sources','online_sessions','account_requests',
    'permissions_override','security_events','health_events','business_standards','workers',
    'worker_payments','payroll_periods','job_cost_snapshots','invoices','invoice_payments',
    'known_devices','owner_recovery_events','bookkeeping_ledgers','bookkeeping_rules',
    'bookkeeping_runs','filekeeping_reviews','bookkeeping_alerts','job_applications','application_events'
]

CODE_SECURITY_PATTERNS = {
    'password hashing': ['pbkdf2_hmac','verify_password','secrets.compare_digest'],
    'device cookie token': ['DEVICE_COOKIE_NAME','set_secure_device_cookie','httponly=True','samesite=DEVICE_COOKIE_SAMESITE'],
    'device table': ['known_devices','trusted','blocked'],
    'owner recovery audit': ['owner_recovery_events','owner-recovery'],
    'rate limit/account request safety': ['request_rate_limited','account_request_rate_limit','password_quality'],
    'role permissions': ['PERMISSIONS','admin','manager','worker','viewer'],
    'application/onboarding': ['job_applications','insurance_full_legal_name','w9_status','id_document_status'],
    'payroll/job costs': ['worker_payments','job_cost_snapshots','invoice_payments'],
    'mobile endpoints': ['api_mobile_dashboard','/mobile','/api/mobile/jobs'],
    'filekeeping/bookkeeping': ['bookkeeping_ledgers','filekeeping_reviews','bookkeeping_alerts'],
}

def timestamp():
    return dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')

class QA:
    def __init__(self):
        self.errors=[]; self.warnings=[]; self.ok=[]; self.fixed=[]
    def add(self, level, component, message):
        line=f'[{level}] {component}: {message}'
        if level=='ERROR': self.errors.append(line)
        elif level=='WARN': self.warnings.append(line)
        elif level=='FIXED': self.fixed.append(line)
        else: self.ok.append(line)
    def run(self):
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        self.check_dirs()
        self.check_files()
        self.compile_python()
        self.check_network_routes_and_security()
        self.check_database()
        self.check_installer_safety()
        self.check_docs()
        return self.write_report()
    def check_dirs(self):
        for d in REQUIRED_DIRS:
            p=BASE_DIR/d
            if not p.exists():
                try:
                    p.mkdir(parents=True, exist_ok=True)
                    self.add('FIXED','Folder',f'Created missing folder {d}')
                except Exception as e:
                    self.add('ERROR','Folder',f'Missing/could not create {d}: {e}')
            else:
                self.add('OK','Folder',f'{d} exists')
    def check_files(self):
        for f in REQUIRED_FILES:
            p=BASE_DIR/f
            if p.exists(): self.add('OK','Required File',f'{f} found')
            else: self.add('ERROR','Required File',f'{f} missing')
    def compile_python(self):
        for p in sorted(APP_DIR.glob('*.py')):
            try:
                ast.parse(p.read_text(encoding='utf-8'))
                self.add('OK','Python Compile',f'{p.name} syntax OK')
            except Exception as e:
                self.add('ERROR','Python Compile',f'{p.name}: {e}')
    def check_network_routes_and_security(self):
        ns=(APP_DIR/'network_server.py').read_text(encoding='utf-8', errors='replace') if (APP_DIR/'network_server.py').exists() else ''
        sc=(APP_DIR/'start_center.py').read_text(encoding='utf-8', errors='replace') if (APP_DIR/'start_center.py').exists() else ''
        for route in REQUIRED_ROUTES:
            if route in ns: self.add('OK','Network Route',f'{route} present')
            else: self.add('WARN','Network Route',f'{route} not found in static scan')
        for name, patterns in CODE_SECURITY_PATTERNS.items():
            missing=[x for x in patterns if x not in ns]
            if missing: self.add('WARN','Security/Feature Pattern',f'{name}: missing static pattern(s): {", ".join(missing)}')
            else: self.add('OK','Security/Feature Pattern',f'{name}: patterns present')
        if 'CREATE_NO_WINDOW' in sc and 'DETACHED_PROCESS' in sc:
            self.add('OK','Launcher', 'Hidden/background process flags are present in Start Center')
        else:
            self.add('WARN','Launcher','Hidden/background process flags not confirmed')
        if 'Full QA' in sc or 'full_program_qa.py' in sc:
            self.add('OK','Launcher','Full QA Test is linked from Start Center')
        else:
            self.add('WARN','Launcher','Full QA Test is not linked from Start Center')
    def check_database(self):
        if not DB_PATH.exists():
            self.add('WARN','Database','Database not found yet. It may be created on first run/System Check.')
            return
        try:
            conn=sqlite3.connect(DB_PATH)
            res=conn.execute('PRAGMA integrity_check').fetchone()[0]
            if res == 'ok': self.add('OK','Database','SQLite integrity check OK')
            else: self.add('ERROR','Database',f'Integrity check result: {res}')
            existing={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for t in REQUIRED_TABLES:
                if t in existing: self.add('OK','Database Table',f'{t} present')
                else: self.add('WARN','Database Table',f'{t} missing; System Check should repair/create it')
            # Simple seed checks
            users=conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='users'").fetchone()[0]
            if users:
                ucount=conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
                self.add('OK' if ucount else 'WARN','Users',f'{ucount} user record(s) found')
            conn.close()
        except Exception as e:
            self.add('ERROR','Database',str(e))
    def check_installer_safety(self):
        ui=BASE_DIR/'install_jr_job_manager_ui.ps1'
        if not ui.exists():
            self.add('ERROR','Installer','install_jr_job_manager_ui.ps1 missing')
            return
        s=ui.read_text(encoding='utf-8', errors='replace')
        safe_names=['data','evidence','exports','backups','chatgpt_imports','business_standards','logs']
        for name in safe_names:
            if name in s: self.add('OK','Installer Data Safety',f'Installer references/preserves {name}')
            else: self.add('WARN','Installer Data Safety',f'Could not confirm preservation handling for {name}')
        if 'does not run Python' in s and 'does not run Python, pip' in s:
            self.add('OK','Installer No-Hang','Installer explicitly states it does not run Python/pip during install')
        elif re.search(r'python\.exe|py\.exe|pip', s, flags=re.I):
            self.add('WARN','Installer No-Hang','Installer appears to reference Python/pip; verify it is not executed during install')
        else:
            self.add('OK','Installer No-Hang','No Python/pip execution found in installer UI script')
        if 'Desktop' in s and 'J and R Construction Manager' in s:
            self.add('OK','Installer Shortcut','Desktop shortcut creation confirmed')
        else:
            self.add('WARN','Installer Shortcut','Could not confirm desktop shortcut creation')
    def check_docs(self):
        docs=['README.txt','START_HERE.txt','NETWORK_AND_MOBILE_TROUBLESHOOTING_V4_4.txt','JOB_APPLICATIONS_INSURANCE_ONBOARDING_V4_2.txt','USER_FRIENDLY_START_AND_HIDDEN_BACKGROUND_V4_5.txt']
        for d in docs:
            if (BASE_DIR/d).exists(): self.add('OK','Documentation',f'{d} present')
            else: self.add('WARN','Documentation',f'{d} missing')
    def write_report(self):
        out=EXPORT_DIR/f'JRC_Full_Program_QA_Report_{timestamp()}.txt'
        lines=[]
        lines.append('J & R Construction Manager - Full Program QA / Business Readiness Report')
        lines.append(f'Generated: {dt.datetime.now().isoformat(timespec="seconds")}')
        lines.append(f'Folder: {BASE_DIR}')
        lines.append('')
        lines.append(f'Summary: {len(self.errors)} error(s), {len(self.warnings)} warning(s), {len(self.fixed)} safe fix(es), {len(self.ok)} OK checks')
        lines.append('')
        for section, rows in [('ERRORS',self.errors),('WARNINGS',self.warnings),('SAFE FIXES',self.fixed),('OK CHECKS',self.ok)]:
            lines.append(section); lines.append('-'*len(section)); lines.extend(rows or ['None']); lines.append('')
        out.write_text('\n'.join(lines), encoding='utf-8')
        print('\n'.join(lines))
        return 1 if self.errors else 0

if __name__ == '__main__':
    sys.exit(QA().run())
