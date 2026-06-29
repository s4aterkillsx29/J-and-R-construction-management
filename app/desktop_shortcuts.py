"""Auto-create desktop shortcuts for the current Windows user."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def ensure_desktop_shortcuts(base_dir: Path | None = None, package_dir: Path | None = None) -> None:
    if os.name != "nt":
        return
    try:
        from app.install_paths import resolve_install_dir
        install_dir = resolve_install_dir(base_dir)
    except Exception:
        install_dir = (base_dir or Path(__file__).resolve().parents[1]).resolve()
    ps1 = install_dir / "scripts" / "Ensure-DesktopShortcuts.ps1"
    if not ps1.exists():
        return
    args = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        str(ps1),
        "-InstallDir",
        str(install_dir),
        "-Quiet",
    ]
    if package_dir:
        args.extend(["-PackageDir", str(package_dir.resolve())])
    try:
        subprocess.run(args, check=False, creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass


def ensure_desktop_shortcuts_async(base_dir: Path | None = None, package_dir: Path | None = None) -> None:
    threading.Thread(
        target=ensure_desktop_shortcuts,
        kwargs={"base_dir": base_dir, "package_dir": package_dir},
        daemon=True,
        name="jrc-desktop-shortcuts",
    ).start()


def read_installer_source(base_dir: Path | None = None) -> Path | None:
    install_dir = (base_dir or Path(__file__).resolve().parents[1]).resolve()
    source_file = install_dir / "INSTALLER_SOURCE.txt"
    if not source_file.exists():
        return None
    try:
        raw = source_file.read_text(encoding="utf-8").strip()
        path = Path(raw)
        return path if raw and path.exists() else None
    except Exception:
        return None
