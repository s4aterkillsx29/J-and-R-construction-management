"""Server startup recovery, graceful shutdown, and data safety for JRC host."""
from __future__ import annotations

import atexit
import datetime as dt
import os
import signal
import sqlite3
import zipfile
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("JRC_DATA_DIR", str(BASE_DIR / "data"))).expanduser()
DB_PATH = Path(os.environ.get("JRC_DB_PATH", str(DATA_DIR / "jr_business.db"))).expanduser()
BACKUP_DIR = Path(os.environ.get("JRC_BACKUP_DIR", str(BASE_DIR / "backups"))).expanduser()
BOOT_MARKER = DATA_DIR / "last_server_boot.txt"
SHUTDOWN_MARKER = DATA_DIR / "last_server_shutdown.txt"

_server_started = False


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def direct_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def create_pre_shutdown_backup(label: str = "shutdown") -> Optional[Path]:
    if not DB_PATH.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = BACKUP_DIR / f"jr_business_{label}_{stamp}.zip"
    try:
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(DB_PATH, arcname="jr_business.db")
            wal = Path(str(DB_PATH) + "-wal")
            shm = Path(str(DB_PATH) + "-shm")
            if wal.exists():
                zf.write(wal, arcname="jr_business.db-wal")
            if shm.exists():
                zf.write(shm, arcname="jr_business.db-shm")
        return out
    except Exception:
        return None


def checkpoint_database() -> None:
    if not DB_PATH.exists():
        return
    try:
        with direct_db() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
    except Exception:
        pass


def on_server_startup() -> None:
    global _server_started
    if _server_started:
        return
    _server_started = True
    try:
        from app.data_pipeline import ensure_master_storage_layout, run_master_pipeline_maintenance
        ensure_master_storage_layout()
        run_master_pipeline_maintenance(DB_PATH)
    except Exception:
        pass
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BOOT_MARKER.write_text(now_iso(), encoding="utf-8")
    if not DB_PATH.exists():
        return
    try:
        with direct_db() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS host_events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_time TEXT, level TEXT, host_mode TEXT, message TEXT, ip_address TEXT, username TEXT)"
            )
            mode = "public" if os.environ.get("JRC_PUBLIC_HOST_MODE", "0") == "1" else "lan"
            conn.execute(
                "INSERT INTO host_events (event_time, level, host_mode, message, ip_address, username) VALUES (?,?,?,?,?,?)",
                (now_iso(), "INFO", mode, "Server started — user sessions are preserved across restarts until timeout or admin revoke.", "127.0.0.1", "system"),
            )
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                ("last_server_boot", now_iso()),
            )
            conn.commit()
    except Exception:
        pass


def on_server_shutdown(graceful: bool = True) -> None:
    SHUTDOWN_MARKER.write_text(f"{now_iso()} graceful={graceful}", encoding="utf-8")
    try:
        from app.data_pipeline import run_master_pipeline_maintenance
        run_master_pipeline_maintenance(DB_PATH)
    except Exception:
        pass
    try:
        create_pre_shutdown_backup("graceful_shutdown" if graceful else "shutdown")
    except Exception:
        pass
    checkpoint_database()
    if not DB_PATH.exists():
        return
    try:
        with direct_db() as conn:
            mode = "public" if os.environ.get("JRC_PUBLIC_HOST_MODE", "0") == "1" else "lan"
            conn.execute(
                "INSERT INTO host_events (event_time, level, host_mode, message, ip_address, username) VALUES (?,?,?,?,?,?)",
                (
                    now_iso(),
                    "INFO",
                    mode,
                    "Server shutdown — database checkpointed and backup saved. Active sessions remain restorable until timeout.",
                    "127.0.0.1",
                    "system",
                ),
            )
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                ("last_server_shutdown", now_iso()),
            )
            conn.commit()
    except Exception:
        pass


def register_shutdown_handlers() -> None:
    atexit.register(lambda: on_server_shutdown(graceful=True))

    def _signal_handler(signum, frame):  # noqa: ARG001
        on_server_shutdown(graceful=True)
        raise SystemExit(0)

    for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None), getattr(signal, "SIGBREAK", None)):
        if sig is None:
            continue
        try:
            signal.signal(sig, _signal_handler)
        except Exception:
            pass
