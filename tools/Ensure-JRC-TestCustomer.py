"""Create or refresh TestCustomer on every local JRC install."""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))


def _install_dirs() -> list[Path]:
    from app.install_paths import legacy_install_dir, owner_install_dir

    seen: set[str] = set()
    out: list[Path] = []
    for p in (BASE, owner_install_dir(), legacy_install_dir(), Path.home() / "Documents" / "JRC" / "J-and-R-construction-management"):
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def main() -> int:
    from app.db_health import sqlite_session
    from app.test_accounts import ensure_test_customer

    ok_all = True
    for install in _install_dirs():
        db = install / "data" / "jr_business.db"
        install.mkdir(parents=True, exist_ok=True)
        (install / "data").mkdir(parents=True, exist_ok=True)
        if install.resolve() == BASE.resolve():
            import os

            os.environ.setdefault("JRC_DATA_DIR", str(install / "data"))
            os.environ.setdefault("JRC_DB_PATH", str(db))
            from app.network_server import init_db

            init_db()
            print(f"{install}: init_db + TestCustomer via init_db")
            continue
        if not db.is_file():
            print(f"{install}: no database — skipped")
            continue
        try:
            with sqlite_session(db) as conn:
                ok, msg = ensure_test_customer(conn)
            print(f"{install}: {msg}")
        except Exception as exc:
            ok_all = False
            print(f"{install}: ERROR {exc}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
