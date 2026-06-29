"""JRC v6.8 Customer Request / Customer Portal final check.
Static checks plus database-schema readiness where available.
"""
from pathlib import Path
import datetime as dt, sqlite3, sys, json
BASE = Path(__file__).resolve().parents[1]
APP = BASE / 'app'
EXPORT = BASE / 'exports'
DATA = BASE / 'data'
EXPORT.mkdir(exist_ok=True)
started = dt.datetime.now().isoformat(timespec='seconds')
report = []
errors = []
warnings = []
passes = []

def check(name, ok, fail_msg=None, warn=False):
    line = ('OK' if ok else ('WARNING' if warn else 'ERROR')) + ' - ' + name
    report.append(line)
    if ok:
        passes.append(name)
    elif warn:
        warnings.append(fail_msg or name)
    else:
        errors.append(fail_msg or name)

ns = (APP/'network_server.py').read_text(encoding='utf-8', errors='ignore')
sc = (APP/'system_check.py').read_text(encoding='utf-8', errors='ignore')

required_customer_fields = [
    'contact_name','contact_phone','contact_email','best_contact_method','property_type','occupancy_status',
    'tenant_name','tenant_phone','appointment_window','safety_notes','pets_notes','budget_range','request_reason','customer_acknowledged'
]
for field in required_customer_fields:
    check(f'customer request field exists: {field}', field in ns and field in sc, f'Missing customer request field/schema repair marker: {field}')

check('customer request schema repair helper exists', 'def ensure_customer_request_schema' in ns, 'Missing ensure_customer_request_schema helper')
check('customer request requires contact method', 'Please provide either a phone number or email' in ns, 'Customer request should require phone or email')
check('customer request acknowledgement required', 'customer_acknowledged' in ns and 'not an approved job' in ns, 'Customer request acknowledgement not enforced')
check('customer request creates event log', 'Customer submitted a complete job request' in ns, 'Customer request event log missing')
check('owner review page includes customer-visible and internal notes', 'customer_visible_notes' in ns and 'internal_notes' in ns and 'customers cannot see this' in ns, 'Owner review separation missing')
check('customer detail hides internal notes', 'internal_notes' not in ns[ns.find('def customer_request_detail'):ns.find('@app.route("/customers/requests"')], 'Customer detail route appears to expose internal notes')
check('customers cannot access internal surfaces helper still exists', 'forbid_customer_external_admin_surface' in ns, 'External/customer internal block helper missing')
rp = (APP/'role_permissions.py').read_text(encoding='utf-8', errors='ignore') if (APP/'role_permissions.py').exists() else ''
customer_perm_ok = (
    '"customer": {"view_dashboard", "mobile_access", "customer_portal", "customer_request_job", "view_customer_shared"}' in ns
    or '"customer": {' in rp and 'customer_portal' in rp and 'view_customer_shared' in rp
)
check('customer role limited permission set exists', customer_perm_ok, 'Customer role permission set changed or too broad')
check('customer dashboard quick actions exist', 'Create Job Request' in ns and 'View My Requests' in ns and 'Customer Dashboard' in ns, 'Customer dashboard quick actions missing')
check('customer route is login protected', '@login_required("customer_request_job")' in ns and '@login_required("customer_portal")' in ns, 'Customer routes missing login protection')
check('owner/admin customer request route protected', '@login_required("manage_applications")' in ns and 'def owner_customer_requests' in ns, 'Owner/admin customer review route not protected')

# Optional database schema check if installed DB exists in build/test folder.
db = DATA/'jr_business.db'
if db.exists():
    try:
        con = sqlite3.connect(db)
        cols = {r[1] for r in con.execute('PRAGMA table_info(customer_job_requests)').fetchall()}
        for field in required_customer_fields:
            check(f'database column present: {field}', field in cols, f'Installed database missing customer column: {field}')
        con.close()
    except Exception as exc:
        check('database schema check', False, f'Database check failed: {exc}', warn=True)
else:
    check('installed database schema live check', False, 'No installed database in clean package environment; System Check repairs columns after install.', warn=True)

summary = f"JRC Customer Request Final Check v6.8\nStarted: {started}\nProgram: {BASE}\n\n" + '\n'.join(report) + f"\n\nSummary: {len(errors)} error(s), {len(warnings)} warning(s), {len(passes)} pass(es).\n"
out = EXPORT / f"JRC_Customer_Request_Final_Check_{dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.txt"
out.write_text(summary, encoding='utf-8')
jsonout = EXPORT / f"JRC_Customer_Request_Final_Check_{dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
jsonout.write_text(json.dumps({'errors': errors, 'warnings': warnings, 'passes': passes, 'report': report}, indent=2), encoding='utf-8')
print(summary)
print('Report saved:', out)
sys.exit(1 if errors else 0)
