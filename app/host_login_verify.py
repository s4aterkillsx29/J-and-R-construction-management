from __future__ import annotations
import json, os, socket, sys, time, urllib.request
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = BASE_DIR / 'exports'; EXPORT_DIR.mkdir(exist_ok=True)
PORT = int(os.environ.get('JRC_PORT','8765'))

def check(url, timeout=1.5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return True, str(r.status), (r.read(250).decode('utf-8','ignore') or 'OK')[:250]
    except Exception as e:
        return False, type(e).__name__, str(e)[:250]

def main():
    base=f'http://127.0.0.1:{PORT}'
    urls=[('/login',base+'/login'),('/api/health',base+'/api/health'),('/mobile/ping',base+'/mobile/ping'),('/api/connection',base+'/api/connection')]
    results=[]
    for name,url in urls:
        ok, code, msg = check(url)
        results.append({'name':name,'url':url,'ok':ok,'code':code,'message':msg})
    login_ok = any(r['name']=='/login' and r['ok'] for r in results)
    stamp=time.strftime('%Y-%m-%d_%H%M%S')
    txt=EXPORT_DIR/f'JRC_Host_Login_Verify_{stamp}.txt'
    js=EXPORT_DIR/f'JRC_Host_Login_Verify_{stamp}.json'
    lines=['JRC Host Login Verify','Created: '+time.strftime('%Y-%m-%d %H:%M:%S'),'Port: '+str(PORT),'']
    for r in results:
        lines.append(f"{r['name']}: {'OK' if r['ok'] else 'FAILED'} - {r['code']} - {r['message']}")
    lines.append('')
    lines.append('Result: '+('LOGIN READY' if login_ok else 'LOGIN NOT READY'))
    txt.write_text('\n'.join(lines),encoding='utf-8')
    js.write_text(json.dumps({'login_ready':login_ok,'results':results},indent=2),encoding='utf-8')
    print('\n'.join(lines))
    return 0 if login_ok else 2
if __name__=='__main__':
    raise SystemExit(main())
