"""JRC v7.1 Quick Setup Final Check.
Verifies local first-login setup, legacy admin/admin compatibility, installer handoff, and core security markers.
"""
from pathlib import Path
import datetime as dt, py_compile, sys, re
BASE=Path(__file__).resolve().parents[1]
APP=BASE/'app'; EXPORT=BASE/'exports'; EXPORT.mkdir(exist_ok=True)
report=EXPORT/(f"JRC_Quick_Setup_Final_Check_{dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.txt")
errors=[]; warnings=[]; notes=[]
def read(rel):
    p=BASE/rel
    if not p.exists():
        errors.append(f"Missing {rel}"); return ''
    notes.append(f"Found {rel}")
    return p.read_text(encoding='utf-8', errors='ignore')
files=['app/local_login_gate.py','app/network_server.py','app/jr_job_manager.py','app/start_center.py','install_jr_job_manager_ui.ps1','INSTALL_J_AND_R_MANAGER.vbs','!!! START INSTALL HERE.vbs']
texts={f:read(f) for f in files}
for py in ['local_login_gate.py','network_server.py','jr_job_manager.py','start_center.py','quick_setup_final_check.py']:
    try:
        py_compile.compile(str(APP/py), doraise=True); notes.append(f"Compiled {py}")
    except Exception as e:
        errors.append(f"Compile failed {py}: {e}")
lg=texts['app/local_login_gate.py']; ns=texts['app/network_server.py']; desk=texts['app/jr_job_manager.py']; inst=texts['install_jr_job_manager_ui.ps1']
checks=[
    ('Local Login Gate creates default admin/admin only when user table is empty', "total == 0" in lg and "DEFAULT_ADMIN_PASSWORD" in lg),
    ('Local Login Gate supports legacy 200000 hashes', "HASH_ITERATIONS_LEGACY" in lg and "200000" in lg),
    ('Local Login Gate migrates legacy hashes after successful login', "Migrated legacy password hash" in lg),
    ('Local Login Gate requires immediate admin password change on default login', "Change admin/admin now" in lg and "change_password_dialog" in lg),
    ('Network server blocks remote default admin/admin', "default_admin_remote_blocked" in ns and "PUBLIC_HOST_MODE" in ns),
    ('Network server supports legacy desktop hashes', "200000" in ns and "Legacy desktop" in ns),
    ('Desktop office supports legacy/current password hashes', "legacy = hashlib.pbkdf2_hmac" in desk),
    ('Installer opens Quick Setup Login without launching heavy Start Center first', "Launching Quick Setup Login only" in inst and "local_login_gate.py" in inst),
    ('Installer version updated to v7.1', "7.1.0 Primary Live Reliable Business Edition" in inst),
    ('Remembered device is opt-in/90-day marker exists', "DEVICE_COOKIE_MAX_AGE_SECONDS" in ns and "90" in ns),
]
for name, ok in checks:
    (notes if ok else errors).append(("OK: " if ok else "FAIL: ")+name)
summary=['JRC v7.1 Quick Setup Final Check', 'Generated: '+dt.datetime.now().isoformat(timespec='seconds'), '', f'Errors: {len(errors)}', f'Warnings: {len(warnings)}', '', 'ERRORS:']
summary += ['- '+e for e in errors] or ['None']
summary += ['', 'WARNINGS:'] + (['- '+w for w in warnings] or ['None'])
summary += ['', 'NOTES:'] + (['- '+n for n in notes] or ['None'])
report.write_text('\n'.join(summary), encoding='utf-8')
print('\n'.join(summary))
sys.exit(1 if errors else 0)
