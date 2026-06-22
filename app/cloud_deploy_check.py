"""JRC cloud deploy readiness checker."""
from __future__ import annotations
import datetime as dt, json, os, sys
from pathlib import Path
BASE_DIR=Path(__file__).resolve().parents[1]
EXPORT_DIR=BASE_DIR/'exports'; EXPORT_DIR.mkdir(exist_ok=True)
checks=[]; warnings=[]; errors=[]
def add(ok,name,detail=''):
    (checks if ok else errors).append((name,detail))

def warn(name,detail=''): warnings.append((name,detail))
for f in ['cloud_hosting/Dockerfile','cloud_hosting/docker-compose.yml','cloud_hosting/render.yaml','cloud_hosting/railway.json','cloud_hosting/fly.toml','cloud_hosting/cloud_entry.py','cloud_hosting/env.example','app/network_server.py','requirements.txt']:
    add((BASE_DIR/f).exists(), f, 'required for cloud/package readiness')
req=(BASE_DIR/'requirements.txt').read_text(errors='replace') if (BASE_DIR/'requirements.txt').exists() else ''
for dep in ['flask','waitress']:
    add(dep in req, f'requirement:{dep}')
# gunicorn may be installed by cloud Docker/render command, not necessarily local requirements
for name, env in [('JRC_PUBLIC_HOST_MODE','1'),('JRC_SECRET_KEY','long random secret'),('JRC_SESSION_TIMEOUT_MINUTES','120')]:
    if os.environ.get(name): checks.append((f'env:{name}','set in current environment'))
    else: warn(f'env:{name}', f'not set here; set on cloud host to {env}')
# source markers
src=(BASE_DIR/'app/network_server.py').read_text(errors='replace')
for marker in ['JRC_SECRET_KEY','PUBLIC_HOST_MODE','Strict-Transport-Security','/api/cloud/status','/cloud-status','customer_portal']:
    add(marker in src, f'source marker:{marker}')
# cloud files content
if (BASE_DIR/'cloud_hosting/Dockerfile').exists():
    txt=(BASE_DIR/'cloud_hosting/Dockerfile').read_text(errors='replace')
    add('gunicorn' in txt, 'Dockerfile uses gunicorn')
    add('JRC_PUBLIC_HOST_MODE=1' in txt, 'Dockerfile public host mode')
if (BASE_DIR/'cloud_hosting/docker-compose.yml').exists():
    txt=(BASE_DIR/'cloud_hosting/docker-compose.yml').read_text(errors='replace')
    add('volumes:' in txt, 'Docker compose persistent volumes')
    add('restart: unless-stopped' in txt, 'Docker compose restart policy')
ts=dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')
report=EXPORT_DIR/f'JRC_Cloud_Deploy_Check_{ts}.txt'
lines=['J & R Construction Manager - Cloud Deploy Check', f'Generated: {dt.datetime.now().isoformat(timespec="seconds")}', f'Result: {len(errors)} errors, {len(warnings)} warnings, {len(checks)} passes','']
if errors: lines += ['ERRORS']+[f'- {n}: {d}' for n,d in errors]+['']
if warnings: lines += ['WARNINGS']+[f'- {n}: {d}' for n,d in warnings]+['']
lines += ['PASSES']+[f'- {n}: {d}' for n,d in checks]
report.write_text('\n'.join(lines), encoding='utf-8')
print(f'Cloud Deploy Check complete: {len(errors)} errors, {len(warnings)} warnings, {len(checks)} passes')
print(report)
if errors: sys.exit(1)
