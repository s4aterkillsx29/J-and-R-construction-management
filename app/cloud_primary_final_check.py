import os, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
APP = ROOT/'app'/'network_server.py'
CH = ROOT/'cloud_hosting'
checks=[]; errors=[]; warnings=[]
def read(p):
    try: return Path(p).read_text(encoding='utf-8',errors='ignore')
    except Exception: return ''
ns=read(APP)
checks.append(('APP_VERSION_CURRENT','7.12.1 Densus' in ns))
checks.append(('CLOUD_PRIMARY_MODE','CLOUD_PRIMARY_MODE' in ns and 'JRC_CLOUD_PRIMARY_MODE' in ns))
checks.append(('CLOUD_DATA_DIR_ENV','JRC_DATA_DIR' in ns and 'JRC_DB_PATH' in ns))
checks.append(('CLOUD_INITIAL_ADMIN','JRC_INITIAL_ADMIN_PASSWORD' in ns and 'cloud initial owner account' in ns.lower()))
checks.append(('DEFAULT_ADMIN_REMOTE_BLOCK','default_admin_remote_blocked' in ns and 'PUBLIC_HOST_MODE' in ns))
checks.append(('SECURITY_HEADERS','Content-Security-Policy' in ns and 'X-Frame-Options' in ns and 'Strict-Transport-Security' in ns))
checks.append(('DEVICE_COOKIE_SECURITY','DEVICE_COOKIE_MAX_AGE_SECONDS' in ns and 'httponly=True' in ns and 'samesite' in ns.lower()))
for f in ['Dockerfile','docker-compose.yml','render.yaml','railway.json','fly.toml','Procfile','env.example','cloud_entry.py']:
    checks.append((f'CLOUD_FILE_{f}',(CH/f).exists()))
render=read(CH/'render.yaml')
checks.append(('RENDER_HEALTHCHECK',('healthCheckPath: /api/live/ready' in render) or ('healthCheckPath: /api/health' in render)))
checks.append(('RENDER_PERSISTENT_DISK','mountPath: /var/data/jrc' in render and 'disks:' in render))
docker=read(CH/'Dockerfile')
checks.append(('GUNICORN_START','gunicorn cloud_hosting.cloud_entry:app' in docker))
checks.append(('PERSISTENT_DATA_PATH','/var/data/jrc' in docker))
for name, ok in checks:
    if not ok: errors.append(name)
if not os.environ.get('JRC_SECRET_KEY'): warnings.append('JRC_SECRET_KEY not set in this environment; set it on the live cloud host.')
if not os.environ.get('JRC_INITIAL_ADMIN_PASSWORD'): warnings.append('JRC_INITIAL_ADMIN_PASSWORD not set here; set it before first cloud deploy.')
if not os.environ.get('JRC_TRUSTED_HOSTS'): warnings.append('JRC_TRUSTED_HOSTS not set here; set it to the live hostname/domain.')
report={'ok':not errors,'errors':errors,'warnings':warnings,'checks':[{'name':n,'ok':o} for n,o in checks]}
out=ROOT/'exports'/'JRC_v7_Cloud_Primary_Final_Check.json'; out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
sys.exit(1 if errors else 0)
