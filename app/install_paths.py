"""Resolve where JRC is installed — Owner Master lives on Desktop by default."""
from __future__ import annotations

import os
from pathlib import Path

FOLDER_NAME = "J and R Construction Manager"
LEGACY_FOLDER_NAME = "J_and_R_Construction_Manager"


def _desktop_dir() -> Path:
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(512)
        # CSIDL_DESKTOPDIRECTORY = 0x10
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0:
            return Path(buf.value)
    except Exception:
        pass
    home = Path.home()
    for candidate in (home / "OneDrive" / "Desktop", home / "Desktop"):
        if candidate.exists():
            return candidate
    return home / "Desktop"


def owner_install_dir() -> Path:
    return _desktop_dir() / FOLDER_NAME


def worker_install_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / LEGACY_FOLDER_NAME


def legacy_install_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / LEGACY_FOLDER_NAME


def resolve_install_dir(hint: Path | str | None = None) -> Path:
    """Find the live install folder (Desktop owner copy preferred)."""
    candidates = []
    if hint:
        candidates.append(Path(hint))
    candidates.extend([owner_install_dir(), legacy_install_dir(), worker_install_dir()])
    seen = set()
    for path in candidates:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if (path / "app" / "network_server.py").exists():
            return path
    return owner_install_dir()


def install_dir_from_profile(profile: str = "") -> Path:
    if profile.lower() in {"workerclient", "worker", "remote"}:
        return worker_install_dir()
    return owner_install_dir()
