"""JRC v7.1 Primary Live Server Check.
Verifies the recommended always-on cloud structure, deployment files, health endpoints,
installer labels, admin login protections, role dashboards, persistent data path, and cloud docs.
"""
from pathlib import Path
import datetime as dt, os
BASE=Path(__file__).resolve().parents[1]
APP=BASE/'app'; CLOUD=BASE/'cloud_hosting'; EXPORTS=BASE/'exports'; EXPORTS.mkdir(exist_ok=True)
errors=[]; warnings=[]; oks=[]
def chk(name, cond, warn=False):
    (oks if cond else warnings if warn else errors).append(name)
def read(p):
    try: return p.read_text(encoding='utf-8', errors='replace')
    except Exception: return ''
ns=read(APP/'network_server.py'); sc=read(APP/'start_center.py'); inst=read(BASE/'install_jr_job_manager_ui.ps1')
render=read(CLOUD/'render.yaml'); docker=read(CLOUD/'Dockerfile'); compose=read(CLOUD/'docker-compose.yml'); env=read(CLOUD/'env.example'); proc=read(CLOUD/'Procfile')
required=[APP/'network_server.py',APP/'start_center.py',APP/'local_login_gate.py',APP/'admin_security_final_check.py',APP/'customer_request_final_check.py',APP/'ui_dashboard_final_check.py',APP/'cloud_primary_final_check.py',CLOUD/'Dockerfile',CLOUD/'render.yaml',CLOUD/'docker-compose.yml',CLOUD/'Procfile',CLOUD/'env.example',CLOUD/'cloud_entry.py']
for f in required: chk('Required file exists: '+str(f.relative_to(BASE)), f.exists())
chk('Version label v7.1 in network server','7.1 Primary Live Reliable Business Edition' in ns)
chk('Version label v7.1 in start center','7.1 Primary Live Reliable Business Edition' in sc)
chk('Installer label v7.1','7.1.0 Primary Live Reliable Business Edition' in inst)
chk('Login-first no-host gate present','local_login_gate.py' in inst and 'Quick Setup Login' in inst)
chk('Default admin not public cloud default','CLOUD_INITIAL_ADMIN_PASSWORD' in ns and 'admin/admin' not in env.lower())
chk('Cloud primary env flag','JRC_CLOUD_PRIMARY_MODE' in env and 'JRC_CLOUD_PRIMARY_MODE' in docker)
chk('Persistent data dir /var/data/jrc configured','/var/data/jrc' in render and '/var/data/jrc' in docker and '/var/data/jrc' in compose)
chk('Render health check path configured','healthCheckPath: /api/live/ready' in render)
chk('Docker uses gunicorn','gunicorn' in docker and 'cloud_hosting.cloud_entry:app' in docker)
chk('Procfile uses gunicorn','gunicorn' in proc)
chk('Live readiness endpoint present','/api/live/ready' in ns and 'primary-live-readiness' in ns)
chk('Role list includes customer and non_company','customer' in ns and 'non_company' in ns)
chk('Customer requests are present','customer_job_requests' in ns and '/customer/request' in ns)
chk('Admin security checks present','admin_security_final_check.py' in sc and 'remote/customer/cloud' in read(APP/'admin_security_final_check.py').lower())
chk('Remembered device opt-in/90 day markers','DEVICE_COOKIE_MAX_AGE_SECONDS' in ns and '90' in ns and 'remember_device' in ns)
chk('Security headers present',all(x in ns for x in ['Content-Security-Policy','X-Frame-Options','X-Content-Type-Options','Referrer-Policy']))
chk('Start Center has Primary Live Server card','Primary Live Server' in sc)
for var in ['JRC_SECRET_KEY','JRC_INITIAL_ADMIN_PASSWORD','JRC_TRUSTED_HOSTS','JRC_CLOUD_BASE_URL']:
    chk('Environment variable set on this machine: '+var, bool(os.environ.get(var)), warn=True)
summary=['JRC v7.1 Primary Live Server Check','Generated: '+dt.datetime.now().isoformat(timespec='seconds'),'','Errors: '+str(len(errors)),'Warnings: '+str(len(warnings)),'','ERRORS:']
summary += ['- '+e for e in errors] or ['- None']
summary += ['','WARNINGS:'] + (['- '+w for w in warnings] or ['- None'])
summary += ['','PASSED:'] + ['- '+o for o in oks]
out='\n'.join(summary)
path=EXPORTS/('JRC_Primary_Live_Server_Check_'+dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')+'.txt')
path.write_text(out,encoding='utf-8')
print(out)
raise SystemExit(1 if errors else 0)
