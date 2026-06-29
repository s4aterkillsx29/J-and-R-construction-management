"""Master owner PC registration and secure admin recognition."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("JRC_DATA_DIR", str(BASE_DIR / "data"))).expanduser()
MASTER_OWNER_FILE = DATA_DIR / "master_owner_device.json"
OWNER_USERNAME = os.environ.get("JRC_OWNER_USERNAME", "admin").strip().lower()


def _device_fingerprint() -> str:
    import platform
    raw = "|".join([
        platform.node(),
        os.environ.get("USERNAME", ""),
        os.environ.get("COMPUTERNAME", ""),
        platform.machine(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def register_master_owner_device(username: str, conn: Optional[sqlite3.Connection] = None) -> bool:
    if username.lower() != OWNER_USERNAME:
        return False
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fp = _device_fingerprint()
    payload = {
        "owner_username": OWNER_USERNAME,
        "device_fingerprint": fp,
        "device_label": os.environ.get("COMPUTERNAME", "Owner PC"),
        "registered_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "note": "Master owner workstation — full business data allowed on this PC only.",
    }
    MASTER_OWNER_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if conn is not None:
        try:
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                ("master_owner_device_fingerprint", fp),
            )
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                ("master_owner_registered", payload["registered_at"]),
            )
            conn.commit()
        except Exception:
            pass
    return True


def is_master_owner_device() -> bool:
    if not MASTER_OWNER_FILE.exists():
        return False
    try:
        data = json.loads(MASTER_OWNER_FILE.read_text(encoding="utf-8"))
        return data.get("device_fingerprint") == _device_fingerprint()
    except Exception:
        return False


def owner_login_trust_level(username: str, ip_address: str) -> str:
    """Returns master | trusted | remote for admin login audit."""
    if username.lower() != OWNER_USERNAME:
        return "standard"
    if is_master_owner_device():
        return "master"
    if ip_address in ("127.0.0.1", "::1"):
        return "trusted"
    return "remote"


def business_data_allowed_locally() -> bool:
    """Business DB/files should only persist on master owner PC unless admin explicitly allows."""
    try:
        from app.data_pipeline import business_data_allowed_locally as pipeline_allowed
        return pipeline_allowed()
    except Exception:
        pass
    profile = DATA_DIR / "install_profile.json"
    if profile.exists():
        try:
            p = json.loads(profile.read_text(encoding="utf-8"))
            if p.get("profile") == "WorkerClient":
                return False
            if p.get("allow_local_business_data") is False:
                return False
        except Exception:
            pass
    return is_master_owner_device() or not profile.exists()
