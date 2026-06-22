"""JRC v7.1 Cloud Primary final UI check.
Checks that Start Center and web dashboards use responsive, visible button layouts.
"""
from pathlib import Path
import time
BASE = Path(__file__).resolve().parents[1]
APP = BASE / 'app'
EXPORTS = BASE / 'exports'

def main():
    errors=[]; warnings=[]; ok=[]
    sc=(APP/'start_center.py').read_text(encoding='utf-8', errors='replace')
    ns=(APP/'network_server.py').read_text(encoding='utf-8', errors='replace')
    checks={
        'Start Center has scrollable canvas': 'tk.Canvas' in sc and 'yscrollcommand' in sc and 'scrollregion' in sc,
        'Start Center cards have visible Open button': 'text="Open"' in sc and 'sticky="ew"' in sc,
        'Start Center version is v7.1': '7.1 Primary Live Reliable Business Edition' in sc,
        'Web dashboard action grid exists': '.action-grid' in ns and 'grid-template-columns:repeat(auto-fit' in ns,
        'Web dashboard buttons have min height': 'min-height:44px' in ns and 'min-height:48px' in ns,
        'Customer dashboard quick actions exist': 'Create Job Request' in ns and 'View My Requests' in ns,
        'External dashboard remains limited': 'External Access Center' in ns and 'specifically shared by J&R' in ns,
        'Admin dashboard command center exists': 'Owner Command Center' in ns and 'Users / Admin' in ns,
        'Manager dashboard command center exists': 'Manager Command Center' in ns and 'Customer Requests' in ns,
        'Network server version is v7.1': '7.1 Primary Live Reliable Business Edition' in ns,
    }
    for name, passed in checks.items():
        (ok if passed else errors).append(name)
    EXPORTS.mkdir(exist_ok=True)
    out = EXPORTS / f"JRC_UI_Dashboard_Final_Check_{time.strftime('%Y-%m-%d_%H%M%S')}.txt"
    lines = ['JRC UI Dashboard Final Check', time.strftime('%Y-%m-%d %H:%M:%S'), '', 'OK:']
    lines += [f'  - {x}' for x in ok]
    lines += ['', 'WARNINGS:'] + ([f'  - {x}' for x in warnings] or ['  - None'])
    lines += ['', 'ERRORS:'] + ([f'  - {x}' for x in errors] or ['  - None'])
    out.write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))
    return 1 if errors else 0
if __name__ == '__main__':
    raise SystemExit(main())
