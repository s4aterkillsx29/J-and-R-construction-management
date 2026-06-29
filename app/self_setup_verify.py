"""
JRC Manager Self Setup + Verification
Runs safe post-install checks automatically and writes a plain-English report.
Does not collect or store passwords. Login remains inside the app.
"""
from __future__ import annotations
import subprocess, sys, os, json, time, traceback
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BASE_DIR / 'app'
EXPORT_DIR = BASE_DIR / 'exports'
LOG_DIR = BASE_DIR / 'logs'
DATA_DIR = BASE_DIR / 'data'
EXPORT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

CHECKS = [
    ('System Check', APP_DIR / 'system_check.py'),
    ('Emergency Access Check', APP_DIR / 'emergency_access_check.py'),
    ('Permission View Check', APP_DIR / 'permission_view_check.py'),
    ('Dashboard Role Check', APP_DIR / 'dashboard_role_check.py'),
    ('Security Perspective Audit', APP_DIR / 'security_perspective_audit.py'),
    ('Final Program Verify', APP_DIR / 'final_program_verify.py'),
    ('Cloud Deploy Check', APP_DIR / 'cloud_deploy_check.py'),
    ('Auto Host Repair', APP_DIR / 'auto_host_repair.py'),
    ('Live Full Update', APP_DIR / 'live_full_update.py'),
    ('v6 Final Readiness', APP_DIR / 'v6_final_readiness.py'),
]

REQUIRED_DIRS = ['data','exports','evidence','backups','logs','chatgpt_imports','business_standards','file_sources','uploads']

def stamp():
    return time.strftime('%Y-%m-%d_%H%M%S')

def run_check(name, path):
    item = {'name': name, 'script': str(path), 'ok': False, 'returncode': None, 'output_tail': '', 'missing': False}
    if not path.exists():
        item['missing'] = True
        item['output_tail'] = 'Script missing.'
        return item
    try:
        proc = subprocess.run([sys.executable, str(path)], cwd=str(BASE_DIR), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        item['returncode'] = proc.returncode
        item['ok'] = proc.returncode == 0
        out = proc.stdout or ''
        item['output_tail'] = '\n'.join(out.splitlines()[-30:])
    except subprocess.TimeoutExpired as exc:
        item['returncode'] = 'timeout'
        item['output_tail'] = 'Timed out after 120 seconds. This usually means a dependency or host process is stuck.'
    except Exception as exc:
        item['returncode'] = 'error'
        item['output_tail'] = traceback.format_exc()[-3000:]
    return item

def main():
    for d in REQUIRED_DIRS:
        (BASE_DIR / d).mkdir(exist_ok=True)
    results=[]
    for name,path in CHECKS:
        results.append(run_check(name,path))
    errors=[r for r in results if not r['ok']]
    payload={
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'base_dir': str(BASE_DIR),
        'python': sys.executable,
        'errors': len(errors),
        'results': results,
        'next_steps': [
            'Open Start Center.',
            'Use First Setup / Login to start a local login or set cloud access.',
            'Use Cloud Access for remote users when this PC is off.',
            'Change default admin/admin password before sharing access.'
        ]
    }
    txt=[]
    txt.append('J & R Construction Manager - Self Setup + Verification Report')
    txt.append('='*70)
    txt.append('Generated: '+payload['timestamp'])
    txt.append('Install folder: '+payload['base_dir'])
    txt.append('')
    for r in results:
        status='PASS' if r['ok'] else 'NEEDS ATTENTION'
        txt.append(f"[{status}] {r['name']} (return: {r['returncode']})")
        if not r['ok'] or r['output_tail']:
            txt.append(r['output_tail'][:2500])
        txt.append('-'*70)
    if errors:
        txt.append('Overall: Needs attention. Open Start Center > Auto Repair Host or Tools / Repair for details.')
    else:
        txt.append('Overall: Passed available checks in this installed environment.')
    txt.append('Important: Internet/cloud remote access requires a running hosted/cloud/tunnel service and HTTPS.')
    ts=stamp()
    txt_path=EXPORT_DIR / f'JRC_Self_Setup_Verification_{ts}.txt'
    json_path=EXPORT_DIR / f'JRC_Self_Setup_Verification_{ts}.json'
    txt_path.write_text('\n'.join(txt), encoding='utf-8')
    json_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(str(txt_path))
    return 0 if not errors else 1

if __name__ == '__main__':
    raise SystemExit(main())
