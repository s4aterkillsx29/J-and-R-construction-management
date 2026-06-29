"""Keep Desktop/AppData installs aligned with Documents master (code + DB)."""
from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

MASTER_CANDIDATES = (
    Path.home() / "Documents" / "JRC" / "J-and-R-construction-management",
    Path(r"C:\Users\enrag\Documents\JRC\J-and-R-construction-management"),
)


def resolve_master() -> Path | None:
    env = os.environ.get("JRC_MASTER_INSTALL", "").strip()
    if env:
        p = Path(env).expanduser()
        if (p / "app" / "network_server.py").exists():
            return p
    for p in MASTER_CANDIDATES:
        if (p / "app" / "network_server.py").exists():
            return p
    return None


def _sqlite_backup(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".db.syncing")
    if tmp.exists():
        tmp.unlink()
    source = sqlite3.connect(src)
    target = sqlite3.connect(tmp)
    source.backup(target)
    target.commit()
    target.close()
    source.close()
    if dst.exists():
        dst.unlink()
    tmp.replace(dst)


def sync_from_master_if_available(install_dir: Path) -> dict:
    """Sync app code and business DB from master when this is a mirror install."""
    install_dir = Path(install_dir).resolve()
    master = resolve_master()
    result = {"master": str(master) if master else "", "synced": False, "notes": []}
    if not master or master.resolve() == install_dir:
        return result

    master_app = master / "app"
    local_app = install_dir / "app"
    if master_app.exists() and local_app.exists():
        gate = master_app / "local_login_gate.py"
        if gate.exists():
            need = True
            local_gate = local_app / "local_login_gate.py"
            if local_gate.exists() and local_gate.stat().st_mtime >= gate.stat().st_mtime:
                text = local_gate.read_text(encoding="utf-8", errors="ignore")
                need = "get_suggested_admin_username" in text and (
                    "from app.install_setup_log import get_suggested_admin_username" not in text
                )
            if need:
                for py in master_app.glob("*.py"):
                    shutil.copy2(py, local_app / py.name)
                result["notes"].append("app/*.py synced from master")
                result["synced"] = True

    master_db = master / "data" / "jr_business.db"
    local_db = install_dir / "data" / "jr_business.db"
    if master_db.exists():
        sync_db = True
        if local_db.exists():
            try:
                conn = sqlite3.connect(local_db)
                ok = conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                conn.close()
                sync_db = not ok or master_db.stat().st_mtime > local_db.stat().st_mtime
            except sqlite3.Error:
                sync_db = True
        if sync_db:
            _sqlite_backup(master_db, local_db)
            result["notes"].append("jr_business.db synced from master")
            result["synced"] = True
    return result
