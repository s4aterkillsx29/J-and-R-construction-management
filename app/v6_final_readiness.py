from __future__ import annotations
import ast, json, os, re, sqlite3, sys, time, zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BASE_DIR / "app"
EXPORT_DIR = BASE_DIR / "exports"
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
EXPORT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

class Check:
    def __init__(self):
        self.errors=[]; self.warnings=[]; self.ok=[]
    def pass_(self,msg): self.ok.append(msg)
    def warn(self,msg): self.warnings.append(msg)
    def fail(self,msg): self.errors.append(msg)
    def require_file(self, path, label=None):
        p=BASE_DIR/path if isinstance(path,str) else path
        if p.exists(): self.pass_(f"FOUND: {label or p.name}")
        else: self.fail(f"MISSING: {label or p}")
    def require_text(self, path, needle, label):
        p=BASE_DIR/path if isinstance(path,str) else path
        try: txt=p.read_text(encoding='utf-8', errors='ignore')
        except Exception as e: self.fail(f"READ FAILED {label}: {e}"); return
        if needle in txt: self.pass_(f"CHECK: {label}")
        else: self.fail(f"MISSING MARKER: {label}")

def py_compile_check(chk: Check):
    for p in APP_DIR.glob('*.py'):
        try:
            ast.parse(p.read_text(encoding='utf-8', errors='ignore'))
            chk.pass_(f"Python syntax OK: {p.name}")
        except Exception as e:
            chk.fail(f"Python syntax FAILED: {p.name}: {e}")

def required_files(chk: Check):
    for rel in [
        'app/start_center.py','app/network_server.py','app/jr_job_manager.py','app/system_check.py',
        'app/permission_view_check.py','app/security_perspective_audit.py','app/dashboard_role_check.py',
        'app/final_program_verify.py','app/cloud_deploy_check.py','app/internet_cloud_security_verify.py',
        'app/self_setup_verify.py','app/auto_host_repair.py','app/host_quick_test.py','app/v6_final_readiness.py',
        'requirements.txt','install_jr_job_manager_ui.ps1','INSTALL_J_AND_R_MANAGER.vbs','!!! START INSTALL HERE.vbs'
    ]: chk.require_file(rel)
    for rel in [
        'cloud_hosting/Dockerfile','cloud_hosting/docker-compose.yml','cloud_hosting/render.yaml',
        'cloud_hosting/railway.json','cloud_hosting/fly.toml','cloud_hosting/Procfile',
        'cloud_hosting/env.example','cloud_hosting/cloudflare_tunnel_example.yml'
    ]: chk.require_file(rel)

def source_markers(chk: Check):
    ns=(BASE_DIR/'app/network_server.py').read_text(encoding='utf-8', errors='ignore')
    sc=(BASE_DIR/'app/start_center.py').read_text(encoding='utf-8', errors='ignore')
    checks=[
        (ns,'SESSION_COOKIE_HTTPONLY','session cookie httponly config'),
        (ns,'SESSION_COOKIE_SAMESITE','session cookie samesite config'),
        (ns,'Content-Security-Policy','Content Security Policy header'),
        (ns,'X-Frame-Options','frame protection header'),
        (ns,'X-Content-Type-Options','nosniff header'),
        (ns,'customer_portal','customer portal permission'),
        (ns,'non_company','non-company external classification'),
        (ns,'customer_job_requests','customer job request table'),
        (ns,'known_devices','remembered-device table'),
        (ns,'DEVICE_COOKIE_MAX_AGE_SECONDS','90-day device cookie setting'),
        (ns,'JRC_TRUSTED_HOSTS','trusted host/cloud setting'),
        (ns,'JRC_SECRET_KEY','cloud secret key setting'),
        (ns,'dropbox_file_source_policy','Dropbox file-source policy'),
        (ns,'/v6-final-readiness','v6 final readiness route'),
        (sc,'run_v6_final_readiness','Start Center v6 readiness button'),
    ]
    for txt, needle, label in checks:
        if needle in txt: chk.pass_(label)
        else: chk.fail(label)

def database_check(chk: Check):
    db_path=DATA_DIR/'jr_business.db'
    if not db_path.exists():
        chk.warn('Installed database not present in package/build environment. This is expected before install or first launch.')
        return
    try:
        conn=sqlite3.connect(db_path); cur=conn.cursor()
        cur.execute('PRAGMA integrity_check'); res=cur.fetchone()[0]
        if str(res).lower()=='ok': chk.pass_('SQLite integrity_check OK')
        else: chk.fail('SQLite integrity_check returned '+str(res))
        for table in ['users','customers','jobs','customer_user_profiles','customer_job_requests','shared_files','shared_jobs','file_sources','known_devices','online_sessions','app_settings']:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(table,))
            if cur.fetchone(): chk.pass_(f'DB table exists: {table}')
            else: chk.fail(f'DB table missing: {table}')
        conn.close()
    except Exception as e:
        chk.fail('Database check failed: '+str(e))

def cloud_files_check(chk: Check):
    env=(BASE_DIR/'cloud_hosting/env.example')
    if env.exists():
        txt=env.read_text(encoding='utf-8', errors='ignore')
        for key in ['JRC_SECRET_KEY','JRC_TRUSTED_HOSTS','JRC_PUBLIC_HOST','JRC_CLOUD_BASE_URL']:
            if key in txt: chk.pass_(f'Cloud env example includes {key}')
            else: chk.warn(f'Cloud env example missing {key}')
    render=(BASE_DIR/'cloud_hosting/render.yaml')
    if render.exists():
        t=render.read_text(encoding='utf-8', errors='ignore').lower()
        if 'gunicorn' in t: chk.pass_('Render blueprint uses gunicorn/production server')
        else: chk.warn('Render blueprint should use gunicorn/production server')

def installer_check(chk: Check):
    ps=(BASE_DIR/'install_jr_job_manager_ui.ps1').read_text(encoding='utf-8', errors='ignore')
    if '6.5.0 Login-First Stable Live Edition' in ps: chk.pass_('Installer version is v6.5')
    else: chk.fail('Installer version not updated to v6.5')
    for preserve in ['data','exports','evidence','chatgpt_imports','backups','logs','business_standards','file_sources','uploads']:
        if preserve in ps: chk.pass_(f'Installer preserves {preserve}')
        else: chk.fail(f'Installer missing preserve folder {preserve}')
    if 'Secure Local Login' in ps or 'local_login_gate.py' in ps: chk.pass_('Installer opens Secure Local Login handoff')
    else: chk.warn('Installer does not open Secure Local Login handoff')
    if 'password' in ps.lower() and 'does not store passwords' in ps.lower(): chk.pass_('Installer documents that it does not store passwords')

def write_report(chk: Check):
    stamp=time.strftime('%Y-%m-%d_%H%M%S')
    report=EXPORT_DIR/f'JRC_v6_Final_Readiness_Report_{stamp}.txt'
    data={
        'version':'6.5 Login-First Stable Live Edition',
        'errors':chk.errors,'warnings':chk.warnings,'passed':chk.ok,
        'summary': {'errors':len(chk.errors),'warnings':len(chk.warnings),'passed':len(chk.ok)}
    }
    lines=[]
    lines.append('J & R Construction Manager v6.5 Final Readiness Report')
    lines.append('Generated: '+time.strftime('%Y-%m-%d %H:%M:%S'))
    lines.append(f"PASSED: {len(chk.ok)} | WARNINGS: {len(chk.warnings)} | ERRORS: {len(chk.errors)}")
    lines.append('\nERRORS')
    lines += ['- '+x for x in chk.errors] or ['- None']
    lines.append('\nWARNINGS')
    lines += ['- '+x for x in chk.warnings] or ['- None']
    lines.append('\nPASSED CHECKS')
    lines += ['- '+x for x in chk.ok]
    report.write_text('\n'.join(lines), encoding='utf-8')
    (EXPORT_DIR/f'JRC_v6_Final_Readiness_Report_{stamp}.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    print('\n'.join(lines))
    print('\nReport saved:', report)

if __name__=='__main__':
    c=Check()
    required_files(c)
    py_compile_check(c)
    source_markers(c)
    database_check(c)
    cloud_files_check(c)
    installer_check(c)
    write_report(c)
    sys.exit(1 if c.errors else 0)
