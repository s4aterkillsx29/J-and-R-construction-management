"""One-time easy setup for the dedicated 24/7 host laptop.

Run: python -m app.dedicated_host_easy_setup
Or double-click: SETUP_DEDICATED_HOST_LAPTOP.bat on the home PC.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

DEFAULT_OFFICE_DB_CANDIDATES = [
    Path.home() / "Documents" / "JRC" / "J-and-R-construction-management" / "data" / "jr_business.db",
    Path.home() / "OneDrive" / "Desktop" / "J and R Construction Manager" / "data" / "jr_business.db",
]


def find_office_db() -> Path | None:
    for p in DEFAULT_OFFICE_DB_CANDIDATES:
        if p.exists():
            return p
    return None


def ensure_venv() -> bool:
    venv_py = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        return True
    bat = BASE_DIR / "ensure_venv.bat"
    if bat.exists():
        print("Setting up Python (first time only)...")
        r = subprocess.run(["cmd", "/c", str(bat)], cwd=str(BASE_DIR))
        return r.returncode == 0 and venv_py.exists()
    return False


def write_quick_start_readme(lan_hint: str = "") -> Path:
    readme = BASE_DIR / "DEDICATED_HOST_README.txt"
    lines = [
        "J & R CONSTRUCTION — DEDICATED HOST LAPTOP (24/7 SERVER)",
        "=" * 60,
        "",
        "ONE-TIME SETUP (you already ran this if you see this file)",
        "  1. SETUP_DEDICATED_HOST_LAPTOP.bat  — done once",
        "  2. Windows Settings -> Power -> Never sleep (plugged in)",
        "  3. Router -> reserve fixed IP for this laptop (recommended)",
        "",
        "EVERY DAY — START THE SERVER (2 clicks)",
        "  Double-click desktop shortcut:",
        "    START JRC Host Server (24-7)",
        "  OR double-click in this folder:",
        "    START_DEDICATED_HOST_SERVER.bat",
        "",
        "  Keep that window OPEN. Do not close it.",
        "",
        "LOCAL LOGIN ON THIS LAPTOP ONLY",
        "  Browser: http://127.0.0.1:8765/login",
        "  User: jrc_host  |  Password: jrc_host (change after first login)",
        "",
        "JACOB (OWNER) FROM OFFICE LAPTOP OR PHONE",
        "  Use the LAN address shown in the host window when server starts.",
        "  Example: http://192.168.50.60:8765/login",
        "  User: ivygrows (full owner admin)",
        "",
        "STOP THE SERVER",
        "  Close the host window OR press Ctrl+C in that window.",
        "",
        "TROUBLESHOOT",
        "  Run START_DEDICATED_HOST_SERVER.bat again after reboot.",
        "  Only ONE laptop should run the host at a time.",
        "",
    ]
    if lan_hint:
        lines.append(f"Last setup LAN hint: {lan_hint}")
        lines.append("")
    readme.write_text("\n".join(lines), encoding="utf-8")
    return readme


def create_desktop_shortcut() -> str:
    ps1 = BASE_DIR / "scripts" / "Ensure-DedicatedHostShortcuts.ps1"
    if not ps1.exists():
        return "Shortcut script not found — use START_DEDICATED_HOST_SERVER.bat manually."
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps1),
                "-InstallDir",
                str(BASE_DIR),
            ],
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR),
        )
        out = (r.stdout or "").strip()
        return out or "Desktop shortcut created (or already exists)."
    except Exception as exc:
        return f"Shortcut skipped: {exc}"


def get_lan_ip() -> str:
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def run_setup(copy_db: bool = True, office_db: str = "") -> int:
    print("=" * 60)
    print("J & R CONSTRUCTION — DEDICATED HOST LAPTOP SETUP")
    print("=" * 60)
    print()

    if not ensure_venv():
        print("WARNING: Python venv not ready. Run ensure_venv.bat first.")

    from app.host_laptop_roles import setup_pc_profile, PROFILE_DEDICATED

    db_source = office_db.strip()
    if copy_db and not db_source:
        found = find_office_db()
        if found:
            db_source = str(found)
            print(f"Found office database: {db_source}")
        else:
            print("No office database found automatically.")
            print("You can copy later — server will still start with a fresh DB.")
            db_source = ""

    results = setup_pc_profile(
        BASE_DIR,
        PROFILE_DEDICATED,
        copy_db_from=db_source,
    )
    for line in results:
        print(f"  {line}")

    lan = get_lan_ip()
    readme = write_quick_start_readme(lan_hint=f"http://{lan}:8765")
    print(f"\n  Wrote: {readme}")

    shortcut_msg = create_desktop_shortcut()
    print(f"  {shortcut_msg}")

    try:
        from app.host_laptop_roles import save_host_settings
        save_host_settings(
            {
                "dedicated_host_lan_url": f"http://{lan}:8765",
                "dedicated_host_setup_complete": True,
                "setup_notes": "Run START_DEDICATED_HOST_SERVER.bat daily. Keep window open.",
            },
            BASE_DIR,
        )
    except Exception:
        pass

    print()
    print("=" * 60)
    print("SETUP COMPLETE")
    print("=" * 60)
    print()
    print("NEXT STEPS:")
    print("  1. Windows -> Power -> Never sleep when plugged in")
    print("  2. Double-click: START JRC Host Server (24-7) on Desktop")
    print("     OR: START_DEDICATED_HOST_SERVER.bat in this folder")
    print(f"  3. On office laptop, save remote URL: http://{lan}:8765")
    print("     (Start Center -> Host Laptop Setup -> paste that URL)")
    print()
    print("Local login on THIS laptop: hostadmin (or jrc_host)")
    print("Owner login from office:    ivygrows at the LAN URL above")
    print()
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Easy dedicated host laptop setup")
    parser.add_argument("--no-copy-db", action="store_true", help="Skip copying office database")
    parser.add_argument("--office-db", default="", help="Path to office jr_business.db")
    args = parser.parse_args(argv)
    return run_setup(copy_db=not args.no_copy_db, office_db=args.office_db)


if __name__ == "__main__":
    raise SystemExit(main())
