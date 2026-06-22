"""JRC v6.4 Extreme Final Verify.
Checks the final live-ready package for the specific owner/admin, install, security, cloud,
file-source, and dashboard requirements. Designed to run on the installed PC after setup too.
"""
from __future__ import annotations
import os, re, json, sqlite3, time, zipfile
from pathlib import Path
BASE = Path(__file__).resolve().parents[1]
APP = BASE / 'app'
EXPORTS = BASE / 'exports'
DATA = BASE / 'data'
EXPORTS.mkdir(exist_ok=True)

def read(p: Path) -> str:
    try: return p.read_text(encoding='utf-8', errors='ignore')
    except Exception: return ''

def has(p: str) -> bool: return (BASE / p).exists()

def check():
    errors=[]; warnings=[]; ok=[]
    ns=read(APP/'network_server.py')
    sc=read(APP/'start_center.py')
    inst=read(BASE/'install_jr_job_manager_ui.ps1')
    # required files
    required=[
        'app/network_server.py','app/start_center.py','app/system_check.py','app/self_setup_verify.py',
        'app/final_program_verify.py','app/cloud_deploy_check.py','app/internet_cloud_security_verify.py',
        'app/admin_security_final_check.py','app/permission_view_check.py','app/dashboard_role_check.py',
        'app/security_perspective_audit.py','app/live_deployment_readiness.py','app/v6_final_readiness.py',
        'app/first_run_login_setup.py','app/host_login_verify.py','app/auto_host_repair.py',
        'app/extreme_final_verify.py','INSTALL_J_AND_R_MANAGER.vbs','install_jr_job_manager_ui.ps1',
        '!!! START INSTALL HERE.vbs','cloud_hosting/Dockerfile','cloud_hosting/docker-compose.yml',
        'cloud_hosting/render.yaml','cloud_hosting/railway.json','cloud_hosting/fly.toml','cloud_hosting/Procfile',
        'cloud_hosting/env.example','cloud_hosting/cloudflare_tunnel_example.yml'
    ]
    for r in required:
        (ok if has(r) else errors).append(('OK required file ' if has(r) else 'MISSING required file ')+r)
    # installer security
    for marker in ['Pre-Install Local Login Check','Open-ExistingSecureLoginCheck','installer does not store passwords','Secure Local Login']:
        (ok if marker in inst else errors).append(('OK installer marker ' if marker in inst else 'MISSING installer marker ')+marker)
    if 'Read-Host' in inst or 'ConvertTo-SecureString' in inst:
        warnings.append('Installer appears to prompt for credential-like input; review manually. Best practice is app login, not installer password storage.')
    else:
        ok.append('Installer does not prompt for password input directly.')
    # admin default protections
    for marker in ['admin_default_password_changed','default_admin_remote_blocked','is_local_setup_request','admin_default_login_disabled_after_change','owner_setup_complete']:
        (ok if marker in ns else errors).append(('OK admin/default protection ' if marker in ns else 'MISSING admin/default protection ')+marker)
    # password changing current password
    for marker in ['Current password', 'verify_password(current, user["salt"], user["password_hash"])', 'session.clear']:
        if marker not in ns:
            warnings.append('Could not confirm change-password marker: '+marker)
    # remembered device 90 days
    for marker in ['remember_device', 'DEVICE_COOKIE_MAX_AGE_SECONDS', 'httponly=True', 'samesite']:
        (ok if marker in ns.lower() or marker in ns else errors).append(('OK device cookie marker ' if (marker in ns.lower() or marker in ns) else 'MISSING device cookie marker ')+marker)
    # account roles
    for role in ['admin','manager','worker','viewer','non_company','customer']:
        (ok if role in ns else errors).append(('OK role ' if role in ns else 'MISSING role ')+role)
    # customer safety
    for marker in ['/customer/request','/customer/requests','customer_visible_notes','internal_notes']:
        (ok if marker in ns else errors).append(('OK customer portal marker ' if marker in ns else 'MISSING customer portal marker ')+marker)
    # cloud/security headers
    for marker in ['Content-Security-Policy','X-Frame-Options','X-Content-Type-Options','Strict-Transport-Security','JRC_SECRET_KEY','JRC_TRUSTED_HOSTS','JRC_CLOUD_BASE_URL']:
        (ok if marker in ns else errors).append(('OK security/cloud marker ' if marker in ns else 'MISSING security/cloud marker ')+marker)
    # file sources
    for marker in ['Dropbox - Invoices2026 1.0','Dropbox - J and R Construction','Dropbox - JRC','ChatGPT Imports','Program Evidence']:
        (ok if marker in ns else warnings).append(('OK file source marker ' if marker in ns else 'WARN file source marker not confirmed ')+marker)
    # database real-world notes
    dbp=DATA/'jr_business.db'
    if dbp.exists():
        try:
            conn=sqlite3.connect(dbp); conn.row_factory=sqlite3.Row
            row=conn.execute("SELECT username, role, active FROM users WHERE username='admin'").fetchone()
            if row and row['role']=='admin' and row['active']:
                ok.append('Installed database admin account exists and is active.')
            else:
                warnings.append('Installed database admin account is missing/inactive; run System Check/Owner Recovery on trusted local PC.')
            conn.close()
        except Exception as e:
            warnings.append('Installed database check skipped/failed: '+str(e))
    else:
        warnings.append('No installed database in this package environment yet; this is expected before install/open.')
    # Output
    stamp=time.strftime('%Y-%m-%d_%H%M%S')
    txt=EXPORTS/f'JRC_Extreme_Final_Verify_{stamp}.txt'
    payload={'timestamp':time.strftime('%Y-%m-%d %H:%M:%S'), 'errors':errors, 'warnings':warnings, 'ok':ok}
    txt.write_text('JRC Extreme Final Verify v6.5\n'+('='*60)+'\nERRORS:\n'+'\n'.join(errors or ['None'])+'\n\nWARNINGS:\n'+'\n'.join(warnings or ['None'])+'\n\nOK CHECKS:\n'+'\n'.join(ok), encoding='utf-8')
    (EXPORTS/f'JRC_Extreme_Final_Verify_{stamp}.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(f'Errors: {len(errors)}')
    print(f'Warnings: {len(warnings)}')
    print(f'Report: {txt}')
    return 1 if errors else 0
if __name__=='__main__':
    raise SystemExit(check())
