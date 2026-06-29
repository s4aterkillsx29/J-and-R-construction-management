"""Bridge between J & R Construction Manager and desktop Densus (admin / localhost only)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]


def _desktop_path() -> Path:
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(512)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0:
            return Path(buf.value)
    except Exception:
        pass
    home = Path.home()
    for p in (home / "OneDrive" / "Desktop", home / "Desktop"):
        if p.exists():
            return p
    return home / "Desktop"


def resolve_densus_install() -> Optional[Path]:
    candidates = [
        _desktop_path() / "Densus",
        BASE_DIR.parent / "Densus",
        Path(os.environ.get("DENSUS_INSTALL_DIR", "")),
    ]
    for p in candidates:
        if p and (p / "app" / "densus_main.py").exists():
            return p.resolve()
    return None


def densus_installed() -> bool:
    return resolve_densus_install() is not None


def _densus_python(install: Path) -> str:
    py = install / ".venv" / "Scripts" / "python.exe"
    return str(py) if py.exists() else sys.executable


def launch_densus_desktop() -> Tuple[bool, str]:
    install = resolve_densus_install()
    if not install:
        return False, "Densus is not installed on this PC. Install from Documents\\JRC\\Densus to Desktop\\Densus."
    for name in ("Launch-Densus.bat", "!!! START DENSUS.vbs"):
        launcher = install / name
        if launcher.exists():
            try:
                if launcher.suffix.lower() == ".vbs":
                    subprocess.Popen(
                        ["wscript.exe", str(launcher)],
                        cwd=str(install),
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                else:
                    subprocess.Popen(
                        ["cmd.exe", "/c", str(launcher)],
                        cwd=str(install),
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                return True, f"Opened Densus from {install}"
            except Exception as exc:
                return False, str(exc)
    return False, "Densus launcher not found in install folder."


def run_densus_troubleshooter() -> Tuple[bool, str]:
    install = resolve_densus_install()
    if not install:
        return False, "Densus not installed on Desktop."
    try:
        proc = subprocess.run(
            [_densus_python(install), "-m", "app.troubleshooter"],
            cwd=str(install),
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (proc.stdout or proc.stderr or "").strip()
        return proc.returncode == 0, out[-1500:] if out else "Densus troubleshooter finished."
    except Exception as exc:
        return False, str(exc)


def run_densus_quick_scan_local() -> Tuple[bool, str]:
    install = resolve_densus_install()
    if not install:
        return False, "Desktop Densus not found."
    script = install / "app" / "quick_scan.py"
    if not script.exists():
        return False, "Update Densus to v2.0 for quick scan."
    try:
        proc = subprocess.run(
            [_densus_python(install), str(script)],
            cwd=str(install),
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (proc.stdout or proc.stderr or "").strip()
        return proc.returncode == 0, out[-3000:] if out else "Scan finished."
    except Exception as exc:
        return False, str(exc)
