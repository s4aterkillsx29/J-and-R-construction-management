"""Dual-laptop hosting: office PC or dedicated 24/7 host PC.

Office laptop (OwnerMaster): can run local host OR connect to remote dedicated host.
Dedicated host laptop (DedicatedHost): runs server 24/7; local login as jrc_host for host ops.
Owner (ivygrows) signs in from office laptop browser to whichever host is running.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]

PROFILE_OWNER = "OwnerMaster"
PROFILE_DEDICATED = "DedicatedHost"
PROFILE_WORKER = "WorkerClient"

ROLE_OWNER_OFFICE = "owner_office"
ROLE_DEDICATED_HOST = "dedicated_host"

DEFAULT_HOST_ADMIN_USERNAME = "jrc_host"
DEFAULT_HOST_ADMIN_PASSWORD = "jrc_host"

SETTINGS_NAME = "local_host_settings.json"
PROFILE_NAME = "install_profile.json"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def data_dir(base_dir: Optional[Path] = None) -> Path:
    root = Path(base_dir or BASE_DIR).resolve()
    if base_dir is not None:
        return root / "data"
    return Path(os.environ.get("JRC_DATA_DIR", str(root / "data"))).expanduser()


def settings_path(base_dir: Optional[Path] = None) -> Path:
    return data_dir(base_dir) / SETTINGS_NAME


def profile_path(base_dir: Optional[Path] = None) -> Path:
    return data_dir(base_dir) / PROFILE_NAME


def load_host_settings(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    fp = settings_path(base_dir)
    if not fp.exists():
        return {}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_host_settings(updates: Dict[str, Any], base_dir: Optional[Path] = None) -> Dict[str, Any]:
    fp = settings_path(base_dir)
    fp.parent.mkdir(parents=True, exist_ok=True)
    merged = load_host_settings(base_dir)
    merged.update(updates)
    merged["updated_at"] = _now()
    fp.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged


def load_install_profile(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    fp = profile_path(base_dir)
    if not fp.exists():
        return {}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_install_profile(
    base_dir: Path,
    profile: str,
    *,
    host_pc_role: str = "",
    notes: str = "",
) -> Path:
    root = Path(base_dir).resolve()
    fp = profile_path(root)
    fp.parent.mkdir(parents=True, exist_ok=True)
    role = host_pc_role or (ROLE_DEDICATED_HOST if profile == PROFILE_DEDICATED else ROLE_OWNER_OFFICE)
    payload = {
        "profile": profile,
        "host_pc_role": role,
        "allow_local_business_data": profile != PROFILE_WORKER,
        "can_run_local_host": profile != PROFILE_WORKER,
        "configured_at": _now(),
        "computer_name": os.environ.get("COMPUTERNAME", ""),
        "notes": notes or {
            PROFILE_OWNER: "Office laptop — Cursor, Dropbox office, can host or use remote host.",
            PROFILE_DEDICATED: "Dedicated home host laptop — 24/7 LAN server; local jrc_host admin.",
            PROFILE_WORKER: "Worker client — browser only.",
        }.get(profile, ""),
    }
    fp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    save_host_settings(
        {
            "host_pc_role": role,
            "can_run_local_host": profile != PROFILE_WORKER,
            "install_profile": profile,
        },
        root,
    )
    return fp


def get_host_pc_role(base_dir: Optional[Path] = None) -> str:
    profile = load_install_profile(base_dir)
    if profile.get("host_pc_role"):
        return str(profile["host_pc_role"])
    settings = load_host_settings(base_dir)
    if settings.get("host_pc_role"):
        return str(settings["host_pc_role"])
    if profile.get("profile") == PROFILE_DEDICATED:
        return ROLE_DEDICATED_HOST
    return ROLE_OWNER_OFFICE


def is_dedicated_host_install(base_dir: Optional[Path] = None) -> bool:
    profile = load_install_profile(base_dir)
    return profile.get("profile") == PROFILE_DEDICATED or get_host_pc_role(base_dir) == ROLE_DEDICATED_HOST


def is_owner_office_install(base_dir: Optional[Path] = None) -> bool:
    profile = load_install_profile(base_dir)
    return profile.get("profile") in (PROFILE_OWNER, "") or get_host_pc_role(base_dir) == ROLE_OWNER_OFFICE


def normalize_host_url(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if not u:
        return ""
    if not u.startswith("http"):
        u = "http://" + u
    return u


def get_remote_host_url(base_dir: Optional[Path] = None) -> str:
    settings = load_host_settings(base_dir)
    return normalize_host_url(settings.get("remote_host_url", "") or settings.get("remote_host_base_url", ""))


def set_remote_host_url(url: str, base_dir: Optional[Path] = None) -> str:
    clean = normalize_host_url(url)
    save_host_settings({"remote_host_url": clean, "remote_host_base_url": clean}, base_dir)
    return clean


def probe_host_url(url: str, timeout: float = 1.8) -> Tuple[bool, Dict[str, Any]]:
    base = normalize_host_url(url)
    if not base:
        return False, {"error": "no_url"}
    health = base + "/api/health"
    try:
        with urllib.request.urlopen(health, timeout=timeout) as resp:
            body = resp.read(8192).decode("utf-8", errors="replace")
            data = json.loads(body) if body.strip().startswith("{") else {}
            ok = resp.status == 200 and data.get("status") == "ok"
            return ok, data if isinstance(data, dict) else {"raw": body[:200]}
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(4096).decode("utf-8", errors="replace")
            data = json.loads(body) if body.strip().startswith("{") else {}
        except Exception:
            data = {}
        return False, {"http_status": exc.code, **(data if isinstance(data, dict) else {})}
    except Exception as exc:
        return False, {"error": str(exc)}


def remote_host_is_running(base_dir: Optional[Path] = None) -> Tuple[bool, str, Dict[str, Any]]:
    url = get_remote_host_url(base_dir)
    if not url:
        return False, "", {}
    ok, data = probe_host_url(url)
    return ok, url, data


def local_host_is_running(port: Optional[int] = None) -> bool:
    try:
        from app.runtime_utils import get_saved_port, is_jrc_server
        p = int(port if port is not None else get_saved_port())
        return is_jrc_server(p)
    except Exception:
        return False


def host_role_label(base_dir: Optional[Path] = None) -> str:
    if is_dedicated_host_install(base_dir):
        return "Dedicated Host Laptop - run server 24/7 here (local login: jrc_host)"
    return "Office Laptop - host here OR connect to remote dedicated host"


def ensure_host_admin_user(conn: sqlite3.Connection, password: Optional[str] = None) -> Tuple[bool, str]:
    """Create jrc_host admin on dedicated host installs (local host operator, not owner)."""
    from app.network_server import hash_password, now_iso

    username = DEFAULT_HOST_ADMIN_USERNAME
    row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if row:
        conn.execute(
            "UPDATE users SET role='admin', active=1, title=? WHERE username=?",
            ("Dedicated Host Operator", username),
        )
        return True, "Host admin jrc_host already exists."
    pwd = password or DEFAULT_HOST_ADMIN_PASSWORD
    salt, ph = hash_password(pwd)
    conn.execute(
        "INSERT INTO users (username, display_name, role, salt, password_hash, active, must_change_password, created_at, notes, email, title, owner_account) "
        "VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?, ?, ?, 0)",
        (
            username,
            "JRC Host Operator",
            "admin",
            salt,
            ph,
            now_iso(),
            "Dedicated host laptop local admin. Manage server on this PC. Jacob uses ivygrows from office laptop browser for full owner admin.",
            "enragementwow@hotmail.com",
            "Host Server Operator",
        ),
    )
    conn.execute(
        "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
        ("dedicated_host_admin_created", _now()),
    )
    return True, f"Created host admin {username} (change password after first login on this PC)."


def copy_office_database(copy_from: Path, base_dir: Path) -> str:
    src = Path(copy_from).expanduser()
    if not src.exists():
        raise FileNotFoundError(f"Database not found: {src}")
    dest_dir = data_dir(base_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "jr_business.db"
    if dest.exists():
        backup = dest_dir / f"jr_business_before_copy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(dest, backup)
    shutil.copy2(src, dest)
    for suffix in ("-wal", "-shm"):
        wal = Path(str(src) + suffix)
        if wal.exists():
            shutil.copy2(wal, Path(str(dest) + suffix))
    return str(dest)


def setup_pc_profile(
    base_dir: Path,
    profile: str,
    *,
    remote_host_url: str = "",
    host_admin_password: str = "",
    copy_db_from: str = "",
) -> List[str]:
    """One-time setup for office or dedicated host laptop."""
    root = Path(base_dir).resolve()
    results: List[str] = []
    if profile not in (PROFILE_OWNER, PROFILE_DEDICATED, PROFILE_WORKER):
        raise ValueError(f"Unknown profile: {profile}")

    role = ROLE_DEDICATED_HOST if profile == PROFILE_DEDICATED else ROLE_OWNER_OFFICE
    fp = write_install_profile(root, profile, host_pc_role=role)
    results.append(f"Install profile: {fp} -> {profile}")

    updates: Dict[str, Any] = {
        "host_pc_role": role,
        "can_run_local_host": profile != PROFILE_WORKER,
        "install_profile": profile,
    }
    if remote_host_url.strip():
        clean = set_remote_host_url(remote_host_url, root)
        updates["remote_host_url"] = clean
        results.append(f"Remote host URL saved: {clean}")
    save_host_settings(updates, root)

    if copy_db_from.strip():
        dest = copy_office_database(Path(copy_db_from), root)
        results.append(f"Copied live database -> {dest}")

    if profile == PROFILE_DEDICATED:
        db_path = data_dir(root) / "jr_business.db"
        if db_path.exists():
            from app.network_server import init_db

            init_db()
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                ok, msg = ensure_host_admin_user(conn, host_admin_password or None)
                conn.commit()
            results.append(msg)
        else:
            results.append("No database yet — start host once to create DB, or copy office DB with --copy-db-from.")

    try:
        from app.data_pipeline import write_pipeline_manifest

        manifest = write_pipeline_manifest()
        results.append(f"Pipeline manifest: {manifest}")
    except Exception as exc:
        results.append(f"Pipeline manifest warning: {exc}")

    results.append(host_role_label(root))
    return results


def pre_start_host_check(base_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """Returns (proceed, message) before starting local host."""
    root = Path(base_dir or BASE_DIR)
    remote_ok, remote_url, remote_data = remote_host_is_running(root)
    local_ok = local_host_is_running()

    if local_ok:
        return True, "Local host is already running on this PC."

    if remote_ok and remote_url:
        version = remote_data.get("version", "?")
        return False, (
            f"Another JRC host is already running at:\n{remote_url}\n\n"
            f"Version: {version}\n\n"
            "Only one host should run at a time.\n"
            "• Office laptop: use Connect to Remote Host instead of starting here.\n"
            "• Switching hosts: stop the remote host first, then start on this PC."
        )

    return True, "OK to start local host on this PC."


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Configure JRC office or dedicated host laptop")
    parser.add_argument("--install-dir", default=str(BASE_DIR))
    parser.add_argument("--profile", choices=[PROFILE_OWNER, PROFILE_DEDICATED], default=PROFILE_DEDICATED)
    parser.add_argument("--remote-host-url", default="", help="Office laptop: URL of dedicated host")
    parser.add_argument("--copy-db-from", default="", help="Dedicated laptop: copy office jr_business.db path")
    parser.add_argument("--host-admin-password", default="", help="Dedicated laptop: jrc_host password (default jrc_host)")
    parser.add_argument("--probe", default="", help="Test if a host URL responds")
    args = parser.parse_args(argv)

    if args.probe:
        ok, data = probe_host_url(args.probe)
        print(json.dumps({"ok": ok, "url": normalize_host_url(args.probe), "data": data}, indent=2))
        return 0 if ok else 1

    lines = setup_pc_profile(
        Path(args.install_dir),
        args.profile,
        remote_host_url=args.remote_host_url,
        host_admin_password=args.host_admin_password,
        copy_db_from=args.copy_db_from,
    )
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
