"""SQLite health checks and lightweight repair for JRC business DB."""
from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional


def configure_sqlite_connection(conn: sqlite3.Connection) -> None:
    """Shared WAL / lock settings for desktop + web using one jr_business.db."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")


@contextmanager
def sqlite_session(
    db_path: Path | str,
    *,
    row_factory: bool = True,
    timeout: float = 15,
) -> Iterator[sqlite3.Connection]:
    """Open SQLite, apply JRC pragmas, commit on success, always close."""
    conn = sqlite3.connect(db_path, timeout=timeout)
    if row_factory:
        conn.row_factory = sqlite3.Row
    configure_sqlite_connection(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _integrity(conn: sqlite3.Connection) -> str:
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "unknown"
    except sqlite3.DatabaseError as exc:
        return str(exc)


def _known_good_db_sources(db_path: Path) -> list[Path]:
    """Other install copies that may have a healthy jr_business.db."""
    home = Path.home()
    candidates = [
        home / "Documents" / "JRC" / "J-and-R-construction-management" / "data" / "jr_business.db",
        home / "OneDrive" / "Desktop" / "J and R Construction Manager" / "data" / "jr_business.db",
        home / "Desktop" / "J and R Construction Manager" / "data" / "jr_business.db",
        home / "projects" / "JRC-Construction-Office" / "local-jrc-app-repo" / "data" / "jr_business.db",
    ]
    out: list[Path] = []
    target = db_path.resolve()
    for c in candidates:
        try:
            if c.is_file() and c.resolve() != target:
                out.append(c)
        except Exception:
            pass
    return out


def _remove_wal_sidecars(db_path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        side = Path(str(db_path) + suffix)
        try:
            if side.is_file():
                side.unlink()
        except Exception:
            pass


def _recover_via_dump(db_path: Path, log_notes: list[str]) -> bool:
    """Rebuild DB from readable pages when integrity_check fails."""
    corrupt = db_path.with_suffix(f".corrupt_{time.strftime('%Y%m%d_%H%M%S')}.db")
    rebuilt = db_path.with_suffix(".rebuilt.db")
    try:
        shutil.copy2(db_path, corrupt)
        log_notes.append(f"archived corrupt copy: {corrupt.name}")
    except Exception as exc:
        log_notes.append(f"archive failed: {exc}")

    _remove_wal_sidecars(db_path)
    try:
        if rebuilt.is_file():
            rebuilt.unlink()
    except Exception:
        pass

    try:
        src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        dst = sqlite3.connect(rebuilt, timeout=30)
        for line in src.iterdump():
            try:
                dst.execute(line)
            except sqlite3.Error:
                pass
        dst.commit()
        src.close()
        dst.close()
        if _integrity(sqlite3.connect(rebuilt, timeout=10)) == "ok":
            shutil.copy2(rebuilt, db_path)
            rebuilt.unlink(missing_ok=True)
            log_notes.append("rebuilt via SQLite dump/recover")
            return True
    except Exception as exc:
        log_notes.append(f"dump recover failed: {exc}")
    try:
        rebuilt.unlink(missing_ok=True)
    except Exception:
        pass
    return False


def _restore_from_source(db_path: Path, src: Path, log_notes: list[str]) -> bool:
    try:
        conn = sqlite3.connect(src, timeout=10)
        if _integrity(conn) != "ok":
            conn.close()
            return False
        conn.close()
        corrupt = db_path.with_suffix(f".corrupt_{time.strftime('%Y%m%d_%H%M%S')}.db")
        if db_path.is_file():
            shutil.copy2(db_path, corrupt)
        _remove_wal_sidecars(db_path)
        shutil.copy2(src, db_path)
        _remove_wal_sidecars(db_path)
        log_notes.append(f"restored from {src.parent.parent.name}")
        return _integrity(sqlite3.connect(db_path, timeout=10)) == "ok"
    except Exception as exc:
        log_notes.append(f"restore from {src} failed: {exc}")
        return False


def ensure_database_healthy(db_path: Path, *, log_dir: Path | None = None) -> tuple[bool, str]:
    """Verify DB integrity; attempt WAL checkpoint / reindex / vacuum / restore on failure."""
    db_path = Path(db_path).resolve()
    if not db_path.is_file():
        return True, "Database file not present yet — will be created on init."

    notes: list[str] = []
    try:
        _remove_wal_sidecars(db_path)
        conn = sqlite3.connect(db_path, timeout=15)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        status = _integrity(conn)
        if status == "ok":
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            conn.close()
            return True, "Database integrity OK."

        notes.append(f"integrity_check: {status[:200]}")
        conn.close()
        _remove_wal_sidecars(db_path)

        conn = sqlite3.connect(db_path, timeout=15)
        for stmt in ("PRAGMA wal_checkpoint(TRUNCATE)", "REINDEX", "VACUUM"):
            try:
                conn.execute(stmt)
                notes.append(f"ran {stmt}")
            except sqlite3.DatabaseError as exc:
                notes.append(f"{stmt} failed: {exc}")
        status = _integrity(conn)
        conn.close()
        if status == "ok":
            return True, "Database repaired: " + "; ".join(notes)

        if _recover_via_dump(db_path, notes):
            return True, "Database rebuilt: " + "; ".join(notes)

        for src in _known_good_db_sources(db_path):
            if _restore_from_source(db_path, src, notes):
                return True, "Database restored from sibling install: " + "; ".join(notes)

        backup_dir = db_path.parent.parent / "backups"
        if backup_dir.is_dir():
            candidates = sorted(backup_dir.glob("**/*jr_business*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
            for src in candidates[:5]:
                if not src.is_file() or src.resolve() == db_path.resolve():
                    continue
                try:
                    test = sqlite3.connect(src, timeout=10)
                    if _integrity(test) != "ok":
                        test.close()
                        continue
                    test.close()
                except Exception:
                    continue
                if _restore_from_source(db_path, src, notes):
                    return True, "Database restored from backup: " + "; ".join(notes)

        msg = "Database still unhealthy after repair: " + "; ".join(notes)
        if log_dir:
            log_dir = Path(log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "db_health_last.log").write_text(msg + "\n", encoding="utf-8")
        return False, msg
    except sqlite3.DatabaseError as exc:
        notes.append(str(exc))
        for src in _known_good_db_sources(db_path):
            if _restore_from_source(db_path, src, notes):
                return True, "Database restored after error: " + "; ".join(notes)
        msg = f"Database error: {exc}"
        if log_dir:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            (Path(log_dir) / "db_health_last.log").write_text(msg + "\n", encoding="utf-8")
        return False, msg


def repair_install_database(install_dir: Path) -> tuple[bool, str]:
    """Repair jr_business.db for an install folder before login."""
    base = Path(install_dir).resolve()
    db_path = base / "data" / "jr_business.db"
    return ensure_database_healthy(db_path, log_dir=base / "logs")


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if args and args[0] in ("--all", "-a"):
        from app.install_paths import legacy_install_dir, owner_install_dir

        paths = {legacy_install_dir(), owner_install_dir(), Path(__file__).resolve().parents[1]}
        ok_all = True
        for p in paths:
            if (p / "data" / "jr_business.db").is_file():
                ok, msg = repair_install_database(p)
                print(f"{p}: {msg}")
                ok_all = ok_all and ok
        return 0 if ok_all else 1
    base = Path(args[0]) if args else Path(__file__).resolve().parents[1]
    ok, msg = repair_install_database(base)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
