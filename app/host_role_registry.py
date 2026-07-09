"""Host PC role registry — set once, suppress repeated 24/7 host nagging."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]

PC_ROLE_OWNER_OFFICE = "owner_office"
PC_ROLE_DEDICATED_HOST = "dedicated_host"
PC_ROLE_REMOTE_CLIENT = "remote_client"

STRATEGY_LOCAL_EMBEDDED = "local_embedded"
STRATEGY_REMOTE_PRIMARY = "remote_primary"
STRATEGY_CLOUD_PRIMARY = "cloud_primary"

DEFAULTS: Dict[str, Any] = {
    "pc_role": PC_ROLE_OWNER_OFFICE,
    "host_strategy": STRATEGY_LOCAL_EMBEDDED,
    "remote_host_url": "",
    "host_check_policy": "on_demand",
    "dedicated_welcome_dismissed": False,
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _data_dir(base_dir: Optional[Path] = None) -> Path:
    root = Path(base_dir or BASE_DIR).resolve()
    if base_dir is not None:
        return root / "data"
    return Path(os.environ.get("JRC_DATA_DIR", str(root / "data"))).expanduser()


def settings_path(base_dir: Optional[Path] = None) -> Path:
    return _data_dir(base_dir) / "local_host_settings.json"


def load_registry(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    fp = settings_path(base_dir)
    merged = dict(DEFAULTS)
    if fp.exists():
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                merged.update(data)
        except Exception:
            pass
    if merged.get("host_pc_role") and not merged.get("pc_role"):
        from app.host_laptop_roles import ROLE_DEDICATED_HOST

        merged["pc_role"] = (
            PC_ROLE_DEDICATED_HOST
            if merged["host_pc_role"] == ROLE_DEDICATED_HOST
            else PC_ROLE_OWNER_OFFICE
        )
    if not merged.get("pc_role"):
        merged["pc_role"] = PC_ROLE_OWNER_OFFICE
    if not merged.get("host_strategy"):
        merged["host_strategy"] = STRATEGY_LOCAL_EMBEDDED
    return merged


def save_registry(updates: Dict[str, Any], base_dir: Optional[Path] = None) -> Dict[str, Any]:
    fp = settings_path(base_dir)
    fp.parent.mkdir(parents=True, exist_ok=True)
    merged = load_registry(base_dir)
    merged.update(updates)
    merged["updated_at"] = _now()
    fp.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    try:
        from app.host_laptop_roles import save_host_settings

        save_host_settings(merged, base_dir)
    except Exception:
        pass
    return merged


def get_pc_role(base_dir: Optional[Path] = None) -> str:
    reg = load_registry(base_dir)
    role = str(reg.get("pc_role") or PC_ROLE_OWNER_OFFICE)
    if role == PC_ROLE_REMOTE_CLIENT:
        return role
    if reg.get('role_confirmed_at'):
        return role
    try:
        from app.host_laptop_roles import ROLE_DEDICATED_HOST, get_host_pc_role

        if get_host_pc_role(base_dir) == ROLE_DEDICATED_HOST:
            return PC_ROLE_DEDICATED_HOST
    except Exception:
        pass
    return role


def get_host_strategy(base_dir: Optional[Path] = None) -> str:
    reg = load_registry(base_dir)
    return str(reg.get("host_strategy") or STRATEGY_LOCAL_EMBEDDED)


def host_role_display(base_dir: Optional[Path] = None) -> str:
    role = get_pc_role(base_dir)
    strategy = get_host_strategy(base_dir)
    role_labels = {
        PC_ROLE_OWNER_OFFICE: "Office PC — local embedded host",
        PC_ROLE_DEDICATED_HOST: "Dedicated Host — 24/7 LAN server",
        PC_ROLE_REMOTE_CLIENT: "Remote client — browser only",
    }
    strategy_labels = {
        STRATEGY_LOCAL_EMBEDDED: "local embedded",
        STRATEGY_REMOTE_PRIMARY: "remote primary",
        STRATEGY_CLOUD_PRIMARY: "cloud primary",
    }
    return f"{role_labels.get(role, role)} · {strategy_labels.get(strategy, strategy)}"


def should_show_dedicated_welcome(base_dir: Optional[Path] = None) -> bool:
    if get_pc_role(base_dir) != PC_ROLE_DEDICATED_HOST:
        return False
    reg = load_registry(base_dir)
    if reg.get("dedicated_welcome_dismissed"):
        return False
    if reg.get("dedicated_host_welcome_shown"):
        return False
    return True


def dismiss_dedicated_welcome(base_dir: Optional[Path] = None) -> None:
    save_registry(
        {"dedicated_welcome_dismissed": True, "dedicated_host_welcome_shown": True},
        base_dir,
    )


def pre_start_host_allowed(base_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """Only block local start when host_strategy=remote_primary and remote host is up."""
    root = Path(base_dir or BASE_DIR)
    try:
        from app.host_laptop_roles import local_host_is_running

        if local_host_is_running():
            return True, "Local host is already running on this PC."
    except Exception:
        pass

    if get_host_strategy(root) != STRATEGY_REMOTE_PRIMARY:
        return True, "OK to start local host on this PC."

    try:
        from app.host_laptop_roles import remote_host_is_running

        remote_ok, remote_url, remote_data = remote_host_is_running(root)
        if remote_ok and remote_url:
            version = remote_data.get("version", "?")
            return False, (
                f"Another JRC host is already running at:\n{remote_url}\n\n"
                f"Version: {version}\n\n"
                "Remote-primary strategy: stop the remote host first, or switch to local embedded."
            )
    except Exception:
        pass
    return True, "OK to start local host on this PC."


def get_poll_interval_ms(base_dir: Optional[Path] = None, *, transitioning: bool = False) -> int:
    if transitioning:
        return 5000
    reg = load_registry(base_dir)
    if reg.get("host_check_policy", "on_demand") == "on_demand":
        return 30000
    return 5000


def confirm_pc_role(
    pc_role: str,
    host_strategy: str = "",
    base_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    updates: Dict[str, Any] = {
        "pc_role": pc_role,
        "role_confirmed_at": _now(),
    }
    if host_strategy:
        updates["host_strategy"] = host_strategy
    root = Path(base_dir or BASE_DIR)
    try:
        from app.host_laptop_roles import (
            PROFILE_DEDICATED,
            PROFILE_OWNER,
            ROLE_DEDICATED_HOST,
            ROLE_OWNER_OFFICE,
            write_install_profile,
        )

        if pc_role == PC_ROLE_DEDICATED_HOST:
            write_install_profile(root, PROFILE_DEDICATED, host_pc_role=ROLE_DEDICATED_HOST)
        elif pc_role == PC_ROLE_OWNER_OFFICE:
            write_install_profile(root, PROFILE_OWNER, host_pc_role=ROLE_OWNER_OFFICE)
    except Exception:
        pass
    return save_registry(updates, root)


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="JRC host PC role registry")
    parser.add_argument("--fix-office-pc", action="store_true", help="Reset to owner_office + local_embedded")
    parser.add_argument("--show", action="store_true", help="Print current registry")
    args = parser.parse_args(argv)
    if args.fix_office_pc:
        confirm_pc_role(PC_ROLE_OWNER_OFFICE, STRATEGY_LOCAL_EMBEDDED)
        print("Set pc_role=owner_office, host_strategy=local_embedded")
        return 0
    if args.show:
        print(json.dumps(load_registry(), indent=2))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
