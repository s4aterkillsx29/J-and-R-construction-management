"""Admin developer tools — manifest verify, tool registry, status reports."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = BASE_DIR / "exports"
EXPORT_DIR.mkdir(exist_ok=True)


def is_admin_developer_pc(base_dir: Path | None = None) -> bool:
    base = Path(base_dir or BASE_DIR).resolve()
    profile = base / "data" / "install_profile.json"
    if profile.exists():
        try:
            data = json.loads(profile.read_text(encoding="utf-8"))
            if data.get("profile") == "OwnerMaster" or data.get("allow_local_business_data"):
                return True
            if data.get("profile") == "WorkerClient":
                return False
        except Exception:
            pass
    auth = base / "data" / "install_auth.json"
    if auth.exists():
        try:
            data = json.loads(auth.read_text(encoding="utf-8"))
            role = str(data.get("role", "")).lower()
            if role == "admin":
                return True
            if role and role != "admin":
                return False
        except Exception:
            pass
    db = base / "data" / "jr_business.db"
    if db.exists():
        try:
            conn = sqlite3.connect(db)
            n = conn.execute("SELECT COUNT(*) FROM users WHERE active=1 AND LOWER(role)='admin'").fetchone()[0]
            conn.close()
            return int(n or 0) > 0
        except Exception:
            return True
    return True


def run_script_hidden(script: Path, log_name: str, cwd: Path | None = None) -> Tuple[int, Path]:
    cwd = Path(cwd or BASE_DIR).resolve()
    logs = cwd / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / log_name
    py = cwd / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)
    startupinfo = None
    flags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with log.open("a", encoding="utf-8", errors="replace") as f:
        f.write(f"\n--- {script.name} {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        proc = subprocess.run(
            [str(py), str(script)],
            cwd=str(cwd),
            stdout=f,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=flags,
            timeout=600,
        )
    return proc.returncode, log


def build_developer_status(base_dir: Path | None = None) -> Dict[str, Any]:
    from app.dependency_tools import dependency_status, status_text
    from app.program_manifest import APP_VERSION, package_status, verify_layout

    base = Path(base_dir or BASE_DIR).resolve()
    ok_files, missing, warnings = verify_layout(base)
    pkgs = package_status()
    deps = dependency_status()
    source = base / "INSTALLER_SOURCE.txt"
    return {
        "version": APP_VERSION,
        "base_dir": str(base),
        "admin_pc": is_admin_developer_pc(base),
        "files_ok": len(ok_files),
        "files_missing": missing,
        "files_warn": warnings,
        "packages": pkgs,
        "optional_deps": deps,
        "dependency_text": status_text(),
        "installer_source": source.read_text(encoding="utf-8").strip() if source.exists() else "",
        "live_data_dir": str(base / "data"),
    }


def write_developer_report(base_dir: Path | None = None) -> Path:
    status = build_developer_status(base_dir)
    base = Path(base_dir or BASE_DIR).resolve()
    export = base / "exports"
    export.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d_%H%M%S")
    txt = export / f"JRC_Admin_Developer_Status_{ts}.txt"
    lines = [
        "J & R Construction Manager — Admin Developer Status",
        "=" * 62,
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Version: {status['version']}",
        f"Install: {status['base_dir']}",
        f"Admin developer PC: {status['admin_pc']}",
        "",
        "PACKAGES",
    ]
    for name, ok in status["packages"].items():
        lines.append(f"  [{'OK' if ok else 'MISSING'}] {name}")
    lines.extend(["", "OPTIONAL MODULES"])
    for name, ok in status["optional_deps"].items():
        lines.append(f"  [{'OK' if ok else 'MISSING'}] {name}")
    if status["files_missing"]:
        lines.extend(["", "MISSING FILES"])
        lines.extend(f"  - {m}" for m in status["files_missing"])
    if status["files_warn"]:
        lines.extend(["", "WARNINGS"])
        lines.extend(f"  - {w}" for w in status["files_warn"])
    if status.get("installer_source"):
        lines.extend(["", f"Installer source: {status['installer_source']}"])
    txt.write_text("\n".join(lines), encoding="utf-8")
    return txt


def run_verify_bundle(base_dir: Path | None = None) -> Tuple[int, Path]:
    from app.program_manifest import VERIFY_SCRIPTS

    base = Path(base_dir or BASE_DIR).resolve()
    export = base / "exports"
    export.mkdir(parents=True, exist_ok=True)
    errors = 0
    report_lines = [f"Verify bundle started {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    for name, rel in VERIFY_SCRIPTS:
        script = base / rel
        if not script.exists():
            report_lines.append(f"[MISSING] {name}: {rel}")
            errors += 1
            continue
        if "host_quick_test" in rel:
            try:
                import os
                import socket

                port = int(os.environ.get("JRC_PORT", "8765"))
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.4)
                host_up = sock.connect_ex(("127.0.0.1", port)) == 0
                sock.close()
                if not host_up:
                    report_lines.append(f"[SKIP] {name} — local host not running (start host first for live endpoint test)")
                    continue
            except Exception:
                pass
        code, log = run_script_hidden(script, f"dev_verify_{script.stem}_last.log", base)
        status = "PASS" if code == 0 else "FAIL"
        report_lines.append(f"[{status}] {name} (exit {code}) log={log.name}")
        if code != 0:
            errors += 1
    ts = time.strftime("%Y-%m-%d_%H%M%S")
    out = export / f"JRC_Developer_Verify_Bundle_{ts}.txt"
    out.write_text("\n".join(report_lines), encoding="utf-8")
    return errors, out


if __name__ == "__main__":
    import sys

    if "--verify-bundle" in sys.argv:
        err, path = run_verify_bundle()
        print(path)
        raise SystemExit(err)
    if "--status" in sys.argv:
        print(write_developer_report())
        raise SystemExit(0)
    raise SystemExit(0)
