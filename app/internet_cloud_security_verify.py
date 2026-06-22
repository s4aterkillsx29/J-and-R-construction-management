"""
Internet / Cloud Security Verification for JRC Manager.
Verifies cloud settings, HTTPS expectation, secrets, safe cookie markers, host header notes, and deployment files.
"""
from __future__ import annotations
import os, json, time, re, sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
APP=BASE/'app'
EXPORT=BASE/'exports'; EXPORT.mkdir(exist_ok=True)
DATA=BASE/'data'; DATA.mkdir(exist_ok=True)

def read(p):
    try: return Path(p).read_text(encoding='utf-8', errors='replace')
    except Exception: return ''

def main():
    checks=[]; warnings=[]; errors=[]
    ns=read(APP/'network_server.py')
    sc=read(APP/'start_center.py')
    cloud_dir=BASE/'cloud_hosting'
    required=['Dockerfile','docker-compose.yml','render.yaml','railway.json','fly.toml','Procfile','env.example','cloudflare_tunnel_example.yml']
    for f in required:
        p=cloud_dir/f
        (checks if p.exists() else errors).append(f'cloud_hosting/{f} exists' if p.exists() else f'MISSING cloud_hosting/{f}')
    markers={
        'environment secret JRC_SECRET_KEY':'JRC_SECRET_KEY' in ns,
        'secure cookie flag helper':'cookie_secure_flag' in ns,
        'HttpOnly cookie usage':('httponly=true' in ns.lower() or 'httponly' in ns.lower()),
        'SameSite cookie usage':'samesite=' in ns.lower(),
        'security headers':'Content-Security-Policy' in ns and 'X-Frame-Options' in ns and 'X-Content-Type-Options' in ns,
        'cloud status endpoint':'/api/cloud/status' in ns,
        'customer portal role':'customer_portal' in ns,
        'non company minimal role':'non_company' in ns,
        'first setup login bridge':'first_run_login_setup.py' in sc or (APP/'first_run_login_setup.py').exists(),
    }
    for name, ok in markers.items():
        (checks if ok else errors).append(('OK ' if ok else 'MISSING ')+name)
    env_example=read(cloud_dir/'env.example')
    if 'JRC_SECRET_KEY' not in env_example: warnings.append('env.example should include JRC_SECRET_KEY for cloud deployments.')
    # HTTP local is acceptable; cloud should be HTTPS. Warn if saved cloud URL is not https.
    cloud_json=DATA/'cloud_connect.json'
    if cloud_json.exists():
        try:
            url=json.loads(read(cloud_json)).get('base_url','')
            if url and not url.startswith('https://'):
                warnings.append('Saved Cloud Access URL is not HTTPS. Use HTTPS for internet users.')
        except Exception as e: warnings.append('Could not parse cloud_connect.json: '+str(e))
    else:
        warnings.append('No saved cloud_connect.json yet. Set Cloud Access after deployment.')
    report={'timestamp':time.strftime('%Y-%m-%d %H:%M:%S'),'errors':errors,'warnings':warnings,'checks':checks}
    ts=time.strftime('%Y-%m-%d_%H%M%S')
    txt=EXPORT/f'JRC_Internet_Cloud_Security_Verify_{ts}.txt'
    js=EXPORT/f'JRC_Internet_Cloud_Security_Verify_{ts}.json'
    lines=['JRC Internet / Cloud Security Verification','='*70,'Generated: '+report['timestamp'],'']
    lines+=['ERRORS:']+(errors or ['None'])+['','WARNINGS:']+(warnings or ['None'])+['','CHECKS:']+checks
    txt.write_text('\n'.join(lines), encoding='utf-8')
    js.write_text(json.dumps(report,indent=2), encoding='utf-8')
    print(txt)
    return 0 if not errors else 1
if __name__=='__main__': raise SystemExit(main())
