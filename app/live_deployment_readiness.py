
"""
J&R Construction Manager v6.3 Local Login + Host Repair Check
Runs without Flask so it can be used before cloud deployment.
Checks live-host package structure, role/perspective markers, secure cookies,
security headers, repair tools, Dropbox/file-source policy, and cloud deploy files.
"""
from __future__ import annotations
import json, os, re, time, hashlib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BASE_DIR / 'app'
CLOUD_DIR = BASE_DIR / 'cloud_hosting'
EXPORT_DIR = BASE_DIR / 'exports'
DATA_DIR = BASE_DIR / 'data'
EXPORT_DIR.mkdir(exist_ok=True)

REQUIRED_FILES = [
    'app/network_server.py','app/start_center.py','app/system_check.py','app/auto_host_repair.py',
    'app/self_setup_verify.py','app/final_program_verify.py','app/cloud_deploy_check.py',
    'app/internet_cloud_security_verify.py','app/dashboard_role_check.py','app/permission_view_check.py',
    'app/security_perspective_audit.py','app/v6_final_readiness.py',
    'cloud_hosting/Dockerfile','cloud_hosting/docker-compose.yml','cloud_hosting/render.yaml',
    'cloud_hosting/railway.json','cloud_hosting/fly.toml','cloud_hosting/Procfile',
    'cloud_hosting/env.example','cloud_hosting/cloudflare_tunnel_example.yml',
    'requirements.txt','INSTALL_J_AND_R_MANAGER.vbs','!!! START INSTALL HERE.vbs'
]
REQUIRED_ROUTES = [
    '/login','/setup-complete','/customer','/customer/request','/customer/requests',
    '/customers/requests','/mobile','/register','/apply','/cloud-status','/api/cloud/status',
    '/api/health','/api/connection','/connect','/security-audit','/v6-final-readiness'
]
ROLE_MARKERS = ['admin','manager','worker','viewer','non_company','customer']
SECURITY_MARKERS = [
    'SESSION_COOKIE_HTTPONLY=True','SESSION_COOKIE_SAMESITE','SESSION_COOKIE_SECURE',
    'Content-Security-Policy','X-Frame-Options','X-Content-Type-Options','Strict-Transport-Security',
    'TRUSTED_HOSTS','JRC_SECRET_KEY','DEVICE_COOKIE_MAX_AGE_SECONDS', 'remember_device'
]
CLOUD_MARKERS = ['gunicorn','JRC_PUBLIC_HOST_MODE','JRC_SECRET_KEY','JRC_TRUSTED_HOSTS','JRC_CLOUD_BASE_URL']
FILE_SOURCE_MARKERS = ['Dropbox', 'chatgpt_imports', 'evidence', 'exports']


def read(rel: str) -> str:
    p = BASE_DIR / rel
    return p.read_text(encoding='utf-8', errors='replace') if p.exists() else ''

def check():
    errors=[]; warnings=[]; passed=[]
    for rel in REQUIRED_FILES:
        if not (BASE_DIR/rel).exists(): errors.append(f'Missing required file: {rel}')
        else: passed.append(f'File present: {rel}')
    ns = read('app/network_server.py')
    sc = read('app/start_center.py')
    cloud_text = '\n'.join(read('cloud_hosting/'+name) for name in ['Dockerfile','docker-compose.yml','render.yaml','railway.json','fly.toml','Procfile','env.example','cloudflare_tunnel_example.yml'])
    for route in REQUIRED_ROUTES:
        if route not in ns: errors.append(f'Missing expected route marker: {route}')
        else: passed.append(f'Route marker present: {route}')
    for role in ROLE_MARKERS:
        if role not in ns: errors.append(f'Missing role marker: {role}')
        else: passed.append(f'Role marker present: {role}')
    for marker in SECURITY_MARKERS:
        if marker not in ns: errors.append(f'Missing security marker: {marker}')
        else: passed.append(f'Security marker present: {marker}')
    for marker in CLOUD_MARKERS:
        if marker not in cloud_text and marker not in ns: errors.append(f'Missing cloud marker: {marker}')
        else: passed.append(f'Cloud marker present: {marker}')
    for marker in FILE_SOURCE_MARKERS:
        if marker.lower() not in (ns+sc+read('app/v6_final_readiness.py')).lower(): warnings.append(f'File-source marker not clearly found: {marker}')
        else: passed.append(f'File-source marker present: {marker}')
    if 'admin/admin' in ns or 'default admin' in (ns+sc).lower():
        passed.append('Default-admin warning/change flow marker present.')
    else:
        warnings.append('Could not find default-admin warning marker.')
    # Cloud env runtime status
    env_status = {
        'JRC_PUBLIC_HOST_MODE': os.environ.get('JRC_PUBLIC_HOST_MODE',''),
        'JRC_CLOUD_BASE_URL': os.environ.get('JRC_CLOUD_BASE_URL',''),
        'JRC_SECRET_KEY_SET': bool(os.environ.get('JRC_SECRET_KEY','')),
        'JRC_TRUSTED_HOSTS': os.environ.get('JRC_TRUSTED_HOSTS',''),
    }
    if not env_status['JRC_SECRET_KEY_SET']:
        warnings.append('Cloud runtime variable JRC_SECRET_KEY is not set in this environment. Set it on the real host.')
    if not env_status['JRC_CLOUD_BASE_URL']:
        warnings.append('JRC_CLOUD_BASE_URL is not set in this environment. Set it after real host URL exists.')
    if not env_status['JRC_TRUSTED_HOSTS']:
        warnings.append('JRC_TRUSTED_HOSTS is not set in this environment. Set it to your real domain on production.')
    result = {
        'program': 'JRC Construction Manager',
        'version': '6.3 Secure Owner Login + Live Final Edition',
        'checked_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'base_dir': str(BASE_DIR),
        'errors': errors,
        'warnings': warnings,
        'passed_count': len(passed),
        'passed_samples': passed[:80],
        'cloud_environment': env_status,
        'recommendation': 'Deploy to a real HTTPS cloud/tunnel/VPN host for remote users. Local host is only for same-Wi-Fi/VPN testing.',
    }
    stamp = time.strftime('%Y-%m-%d_%H%M%S')
    (EXPORT_DIR/f'JRC_v6_3_Live_Deployment_Readiness_{stamp}.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    report = []
    report.append('J&R CONSTRUCTION MANAGER - v6.3 LOCAL LOGIN + HOST REPAIR')
    report.append('='*70)
    report.append(f'Checked: {result["checked_at"]}')
    report.append(f'Errors: {len(errors)}')
    report.append(f'Warnings: {len(warnings)}')
    report.append(f'Passed checks: {len(passed)}')
    report.append('')
    if errors:
        report.append('ERRORS')
        report.extend('- '+e for e in errors)
        report.append('')
    if warnings:
        report.append('WARNINGS / ACTIONS FOR REAL HOST')
        report.extend('- '+w for w in warnings)
        report.append('')
    report.append('LIVE-HOST RULE')
    report.append('- Remote users can connect while your PC is off only when a real cloud/tunnel/VPN server is running.')
    report.append('- Use HTTPS, a strong JRC_SECRET_KEY, JRC_TRUSTED_HOSTS, backups, and role-based dashboards.')
    report.append('')
    report.append('PASSED SAMPLE CHECKS')
    report.extend('- '+p for p in passed[:60])
    out = '\n'.join(report)
    (EXPORT_DIR/f'JRC_v6_3_Live_Deployment_Readiness_{stamp}.txt').write_text(out, encoding='utf-8')
    print(out)
    return 1 if errors else 0

if __name__ == '__main__':
    raise SystemExit(check())
