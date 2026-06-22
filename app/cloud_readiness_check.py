"""
J & R Construction Manager v4.9 Cloud Readiness Check
Checks whether the package contains the files needed for a safer cloud-hosted mobile setup.
This does not connect to a cloud provider or upload private data.
"""
from __future__ import annotations
from pathlib import Path
import datetime as dt, json, os

BASE_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = BASE_DIR / 'exports'
CLOUD_DIR = BASE_DIR / 'cloud_hosting'
REQUIRED = [
    'cloud_hosting/README_CLOUD_HOSTING_JRC.txt',
    'cloud_hosting/Dockerfile',
    'cloud_hosting/docker-compose.yml',
    'cloud_hosting/Procfile',
    'cloud_hosting/render.yaml',
    'cloud_hosting/cloud_entry.py',
    'cloud_hosting/env.example',
    'app/network_server.py',
]

def main() -> int:
    EXPORT_DIR.mkdir(exist_ok=True)
    errors=[]; warnings=[]
    for rel in REQUIRED:
        if not (BASE_DIR/rel).exists():
            errors.append(f'Missing required cloud file: {rel}')
    if not (BASE_DIR/'data').exists():
        warnings.append('Data folder does not exist yet. It will be created on first run/system check.')
    if not (BASE_DIR/'app'/'network_server.py').exists():
        errors.append('network_server.py missing; hosted/mobile web app cannot run.')
    if 'JRC_PUBLIC_HOST_MODE' not in os.environ:
        warnings.append('JRC_PUBLIC_HOST_MODE is not set in this local test. Cloud deployments should set it to 1.')
    report = {
        'created_at': dt.datetime.now().isoformat(timespec='seconds'),
        'program': 'J & R Construction Manager',
        'cloud_ready': not errors,
        'errors': errors,
        'warnings': warnings,
        'next_steps': [
            'Use local host only for same-Wi-Fi or VPN testing.',
            'For remote mobile access, deploy the cloud_hosting folder to a secure cloud/VPS provider with HTTPS.',
            'Change default admin password before public or remote access.',
            'Keep Dropbox as evidence/file storage; do not make Dropbox a live shared database.',
            'Back up database before moving to cloud.'
        ]
    }
    out = EXPORT_DIR / f'JRC_Cloud_Readiness_Report_{dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")}.json'
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    print(f'\nReport saved: {out}')
    return 1 if errors else 0

if __name__ == '__main__':
    raise SystemExit(main())
