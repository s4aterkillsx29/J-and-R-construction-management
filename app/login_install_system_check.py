"""JRC Login/Install System Check v6.5."""
from pathlib import Path
import datetime as dt, py_compile, sys
BASE=Path(__file__).resolve().parents[1]
EXPORT=BASE/'exports'; EXPORT.mkdir(exist_ok=True)
APP=BASE/'app'
REPORT=EXPORT/(f"JRC_Login_Install_System_Check_{dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.txt")
errors=[]; warnings=[]; notes=[]
def check_file(rel):
    p=BASE/rel
    if not p.exists(): errors.append(f'Missing {rel}')
    else: notes.append(f'OK file: {rel}')
for rel in ['app/local_login_gate.py','app/first_run_login_setup.py','app/start_center.py','app/network_server.py','app/emergency_access.py','app/emergency_routes.py','INSTALL_J_AND_R_MANAGER.vbs','install_jr_job_manager_ui.ps1']:
    check_file(rel)
for py in ['local_login_gate.py','first_run_login_setup.py','start_center.py','network_server.py']:
    try: py_compile.compile(str(APP/py), doraise=True); notes.append(f'Compiled {py}')
    except Exception as e: errors.append(f'Compile failed {py}: {e}')
start=(APP/'start_center.py').read_text(encoding='utf-8',errors='ignore')
first=(APP/'first_run_login_setup.py').read_text(encoding='utf-8',errors='ignore')
installer=(BASE/'install_jr_job_manager_ui.ps1').read_text(encoding='utf-8',errors='ignore')
net=(APP/'network_server.py').read_text(encoding='utf-8',errors='ignore')
if 'require_blocking_login' not in start: errors.append('Start Center does not require blocking login (require_blocking_login)')
if 'local_login_gate' not in first: errors.append('First setup does not fall back to local_login_gate')
if 'local_login_gate.py' not in installer: errors.append('Installer does not open local login gate after install')
if 'seed_mastery_key_on_install' not in installer: errors.append('Installer does not seed owner emergency mastery key')
an=(APP/'application_notifications.py').read_text(encoding='utf-8',errors='ignore')
if 'quick_change_user_role' not in net: errors.append('Admin quick account type change missing')
if 'apply_user_role_change' not in net: errors.append('apply_user_role_change helper missing')
if 'role_select_options' not in net: errors.append('Friendly role select options missing')
if 'notify_requester_account_decision' not in an: errors.append('Account request requester notify missing')
if 'Emergency Owner Access' not in (APP/'local_login_gate.py').read_text(encoding='utf-8',errors='ignore'): errors.append('Local login gate missing Emergency Owner Access')
lg=(APP/'local_login_gate.py').read_text(encoding='utf-8',errors='ignore')
if 'get_suggested_admin_username' in lg and 'from app.install_setup_log import get_suggested_admin_username' not in lg:
    errors.append('Local login gate uses get_suggested_admin_username without import')
if '/emergency-access' not in net: errors.append('Network server missing /emergency-access route')
if 'register_emergency_routes' not in net: errors.append('Network server missing register_emergency_routes')
if 'admin_default_password_changed' not in net or 'DEFAULT_ADMIN_PASSWORD' not in net: errors.append('Network server missing admin default preservation/blocking markers')
if 'PUBLIC_HOST_MODE' not in net or 'default_admin_remote_blocked' not in net: errors.append('Remote default-admin blocking marker missing')
if 'DEVICE_COOKIE_MAX_AGE_SECONDS' not in net or '90' not in net: warnings.append('Remembered device 90-day marker not obvious')
summary=['JRC Login/Install System Check','Generated: '+dt.datetime.now().isoformat(timespec='seconds'),'','Errors: '+str(len(errors)),'Warnings: '+str(len(warnings)),'']
summary += ['ERRORS:']+(['- '+e for e in errors] or ['None'])+['','WARNINGS:']+(['- '+w for w in warnings] or ['None'])+['','NOTES:']+(['- '+n for n in notes] or ['None'])
REPORT.write_text('\n'.join(summary),encoding='utf-8')
print('\n'.join(summary))
sys.exit(1 if errors else 0)
