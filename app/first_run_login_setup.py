"""
JRC First Setup / Login Bridge v6.5
Opens a secure local login gate first. The web host is optional and no longer blocks setup.
"""
from __future__ import annotations
import subprocess, sys, urllib.request, json, os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
BASE_DIR=Path(__file__).resolve().parents[1]
APP_DIR=BASE_DIR/'app'; DATA_DIR=BASE_DIR/'data'; LOG_DIR=BASE_DIR/'logs'
for d in [DATA_DIR,LOG_DIR,BASE_DIR/'exports']: d.mkdir(exist_ok=True)
LOCAL_SETTINGS=DATA_DIR/'local_host_settings.json'; DEFAULT_PORT=8765
PYTHONW=BASE_DIR/'.venv'/'Scripts'/'pythonw.exe'; PYTHON=BASE_DIR/'.venv'/'Scripts'/'python.exe'
PY_CMD=str(PYTHONW if PYTHONW.exists() else PYTHON if PYTHON.exists() else sys.executable)
def get_port():
    try:
        if LOCAL_SETTINGS.exists(): return int(json.loads(LOCAL_SETTINGS.read_text(encoding='utf-8')).get('port', DEFAULT_PORT))
    except Exception: pass
    return DEFAULT_PORT
def url_ok(url, timeout=1.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r: return True, r.status
    except Exception as e: return False, str(e)
def launch_py(module_file, log_name):
    log=LOG_DIR/log_name
    with log.open('a',encoding='utf-8',errors='replace') as f:
        f.write('\n--- First Setup Launch ---\n')
        try: return subprocess.Popen([PY_CMD, str(module_file)], cwd=str(BASE_DIR), stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL), log
        except Exception as e:
            f.write('LAUNCH ERROR: '+str(e)+'\n'); return None, log
def launch_host(port):
    log=LOG_DIR/'first_setup_host.log'
    env=os.environ.copy(); env['JRC_PORT']=str(port)
    with log.open('a', encoding='utf-8', errors='replace') as f:
        f.write('\n--- Optional host launch from First Setup ---\n')
        try: return subprocess.Popen([PY_CMD, str(APP_DIR/'network_server.py')],cwd=str(BASE_DIR),stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,env=env), log
        except Exception as e:
            f.write('HOST LAUNCH ERROR: '+str(e)+'\n'); return None, log
def main():
    root=tk.Tk(); root.withdraw()
    msg=("J & R Construction Manager will open Secure Local Login first.\n\n"
         "This does NOT require the local web host to verify. The web host is optional for same-Wi-Fi/mobile testing.\n\n"
         "The installer does not collect or store passwords. Login happens in the local secure login gate or inside the running app.\n\n"
         "Open Secure Local Login now?")
    if messagebox.askyesno('JRC First Setup / Login', msg):
        proc, log = launch_py(APP_DIR/'local_login_gate.py','local_login_gate_from_setup.log')
        if proc is None:
            messagebox.showwarning('Could not open local login', f'Local Login Gate could not open. Log: {log}')
            return 1
    port=get_port(); ok,_=url_ok(f'http://127.0.0.1:{port}/login',.6)
    if not ok:
        launch_host(port)
    messagebox.showinfo('Setup/Login Started', 'Secure Local Login has been opened.\n\nIf you need browser login later, use Start Center > Start Local Host. Local host is optional and should not block your normal setup.')
    return 0
if __name__=='__main__': raise SystemExit(main())
