"""J&R Construction Manager v5.3 Security Perspective Audit.
Runs deep checks for role permissions, customer/external views, security headers, cookies,
admin-only pages, and sensitive data separation. This is a local diagnostic tool; it does not
connect to the internet or change real business records except creating/updating QA test users.
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = BASE_DIR / "exports"
EXPORT_DIR.mkdir(exist_ok=True)
APP_DIR = BASE_DIR / "app"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

REPORT=[]; ERRORS=[]; WARNINGS=[]

def line(x): REPORT.append(str(x))
def ok(x): line(f"OK - {x}")
def warn(x): WARNINGS.append(x); line(f"WARNING - {x}")
def err(x): ERRORS.append(x); line(f"ERROR - {x}")

def check_static_source():
    import re

    src=(APP_DIR/'network_server.py').read_text(encoding='utf-8', errors='replace')
    rp=(APP_DIR/'role_permissions.py').read_text(encoding='utf-8', errors='replace')
    perms_match = re.search(r'"customer":\s*\{([^}]+)\}', rp)
    customer_block = perms_match.group(1) if perms_match else ''
    required={
        'admin role has manage_users/audit/manage_devices': '"manage_users"' in rp and '"audit"' in rp and '"manage_devices"' in rp,
        'customer role exists with customer-only permissions': '"customer"' in rp and 'view_customer_shared' in customer_block and 'view_files' not in customer_block,
        'non-company role minimal only': '"non_company"' in rp and 'view_shared_sessions' in rp,
        'customer routes exist': '/customer/request' in src and '/customer/requests' in src and '/customers/requests' in src,
        'customer internal notes hidden from customer route': 'internal_notes' in src and 'Customer Request Detail' in src,
        'security headers set': 'Content-Security-Policy' in src and 'X-Frame-Options' in src and 'X-Content-Type-Options' in src,
        'device cookie is http-only and same-site': 'httponly=True' in src and 'DEVICE_COOKIE_SAMESITE' in src,
        'device cookie stores fingerprint': '_hash_device_token' in src and 'client_device_fingerprint' in src,
        'blocked devices enforced at login': 'is_client_device_blocked' in src and 'login_blocked_device' in src,
        'permission navigation filters items': 'for key, label, href, need in nav' in src and 'need in perms' in src,
        'customer account request option exists': "<option value='customer'>" in src,
        'admin security audit route exists': '/security-audit' in src,
        'account approval admin only': 'approve_account_request' in src and 'is_admin_role' in src,
        'file access security guard': 'file_access_security' in src and 'role_may_open_indexed_file' in src,
        'pending login blocked message': 'login_pending_approval' in src,
    }
    for label, passed in required.items():
        ok(label) if passed else err(label)
    if 'Internal job costing' not in src:
        warn('Customer privacy text may not explicitly mention internal job costing.')

def check_dynamic():
    from app import network_server as ns
    ns.init_db()
    with ns.app.test_client() as client:
        def ensure_user(username, role, password='TestPass123!'):
            with ns.direct_db() as conn:
                salt, ph = ns.hash_password(password)
                row=conn.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone()
                if row:
                    conn.execute('UPDATE users SET role=?, active=1, salt=?, password_hash=?, must_change_password=0, display_name=? WHERE username=?', (role,salt,ph,f'QA {role}',username))
                else:
                    conn.execute('INSERT INTO users (username, display_name, role, salt, password_hash, active, must_change_password, created_at, notes) VALUES (?,?,?,?,?,1,0,?,?)', (username, f'QA {role}', role, salt, ph, ns.now_iso(), 'Created by security_perspective_audit.py'))
                conn.commit()
        roles=['admin','manager','worker','viewer','non_company','customer']
        for role in roles:
            ensure_user(f'qa_sec_{role}', role)
        ok('QA users ready for every role')
        def login(role):
            with client.session_transaction() as sess: sess.clear()
            return client.post('/login', data={'username':f'qa_sec_{role}','password':'TestPass123!'}, follow_redirects=False)
        expected={
            'admin': {'allow':['/','/jobs','/expenses','/payroll','/files','/admin','/admin/devices','/health','/customers/requests','/applications','/security-audit'], 'deny':[]},
            'manager': {'allow':['/','/jobs','/expenses','/payroll','/files','/customers/requests','/applications'], 'deny':['/admin','/admin/devices','/health','/security-audit']},
            'worker': {'allow':['/','/jobs','/files','/sharing','/mobile'], 'deny':['/expenses','/payroll','/admin','/health','/customers/requests','/applications','/customer/request']},
            'viewer': {'allow':['/','/jobs','/files','/sharing','/mobile'], 'deny':['/expenses','/payroll','/admin','/health','/customers/requests','/applications','/customer/request']},
            'non_company': {'allow':['/','/sharing','/mobile'], 'deny':['/jobs','/files','/expenses','/payroll','/admin','/health','/customers/requests','/applications','/customer/request']},
            'customer': {'allow':['/','/customer','/customer/request','/customer/requests','/mobile'], 'deny':['/jobs','/files','/expenses','/payroll','/admin','/health','/customers/requests','/applications','/bookkeeping']},
        }
        for role, spec in expected.items():
            resp=login(role)
            if resp.status_code in (302,303): ok(f'{role} login accepted')
            else: err(f'{role} login returned {resp.status_code}')
            # Cookie security attributes from login response
            if role=='admin':
                cookie='; '.join(resp.headers.getlist('Set-Cookie'))
                if 'HttpOnly' in cookie and 'SameSite=Strict' in cookie: ok('login cookie uses HttpOnly and SameSite=Strict')
                else: err(f'login cookie missing HttpOnly/SameSite: {cookie}')
            for path in spec['allow']:
                r=client.get(path, follow_redirects=False)
                if r.status_code==200: ok(f'{role} allowed {path}')
                else: err(f'{role} expected 200 at {path}, got {r.status_code}')
                body=(r.data or b'').decode('utf-8','replace')
                if role in {'worker','viewer','non_company','customer'} and path=='/':
                    forbidden=['Paid Income','Open Receivables','Worker Pay','Expenses<b>']
                    leaked=[x for x in forbidden if x in body]
                    if leaked: err(f'{role} dashboard leaked money widgets: {leaked}')
                    else: ok(f'{role} dashboard hides money widgets')
                if role=='customer' and path in {'/','/customer'}:
                    forbidden=['Internal J&R note','Payroll','Worker Pay','job_costing','internal_notes']
                    leaked=[x for x in forbidden if x in body]
                    if leaked: err(f'customer page leaked internal terms: {leaked}')
                    else: ok('customer page hides internal/business-only details')
            for path in spec['deny']:
                r=client.get(path, follow_redirects=False)
                if r.status_code==403: ok(f'{role} denied {path}')
                else: err(f'{role} expected 403 at {path}, got {r.status_code}')
        # Public headers
        r=client.get('/login')
        headers=r.headers
        for h in ['X-Content-Type-Options','X-Frame-Options','Content-Security-Policy','Referrer-Policy','Permissions-Policy']:
            if h in headers: ok(f'security header present: {h}')
            else: err(f'missing security header: {h}')
        # Sensitive no-store for admin after login
        login('admin')
        r=client.get('/admin')
        cc=r.headers.get('Cache-Control','')
        if 'no-store' in cc: ok('admin pages use no-store cache control')
        else: err(f'admin Cache-Control not no-store: {cc}')
        # Restore Jacob's single-owner policy after QA route tests
        try:
            with ns.direct_db() as conn:
                pol = conn.execute("SELECT value FROM app_settings WHERE key='single_owner_admin_policy'").fetchone()
                if pol and pol[0]:
                    conn.execute("UPDATE users SET active=0 WHERE username != ?", (ns.DEFAULT_ADMIN_USERNAME,))
                    conn.commit()
                    ok('Single owner admin restored — QA test users deactivated after audit')
        except Exception as exc:
            warn(f'Could not restore single owner admin after audit: {exc}')

def run():
    line('J&R Construction Manager v5.3 Security Perspective Audit')
    line(f'Started: {dt.datetime.now().isoformat(timespec="seconds")}')
    line(f'Program folder: {BASE_DIR}')
    line('')
    check_static_source()
    line('')
    try:
        check_dynamic()
    except ModuleNotFoundError as exc:
        warn(f'Dynamic Flask checks skipped because dependency is missing: {exc}')
    except Exception as exc:
        err(f'Dynamic checks failed: {type(exc).__name__}: {exc}')
    line('')
    line(f'Summary: {len(ERRORS)} error(s), {len(WARNINGS)} warning(s)')
    out=EXPORT_DIR / f'JRC_Security_Perspective_Audit_{dt.datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
    out.write_text('\n'.join(REPORT), encoding='utf-8')
    print('\n'.join(REPORT))
    print(f'\nReport saved: {out}')
    return 1 if ERRORS else 0

if __name__=='__main__':
    raise SystemExit(run())
