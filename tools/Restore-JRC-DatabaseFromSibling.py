"""Restore a corrupted jr_business.db from a healthy sibling install."""
from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path

SOURCE = Path(r"C:\Users\enrag\Documents\JRC\J-and-R-construction-management\data\jr_business.db")
TARGET = Path(r"C:\Users\enrag\AppData\Local\J_and_R_Construction_Manager\data\jr_business.db")


def main() -> int:
    if not SOURCE.is_file():
        print(f"Healthy source missing: {SOURCE}")
        return 1
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    if TARGET.is_file():
        corrupt = TARGET.with_suffix(f".corrupt_{time.strftime('%Y%m%d_%H%M%S')}.db")
        shutil.copy2(TARGET, corrupt)
        print(f"Backed up corrupt DB to {corrupt}")
        try:
            ck = sqlite3.connect(TARGET, timeout=5)
            ck.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            ck.close()
        except Exception:
            pass
    for ext in ("-wal", "-shm", "-journal"):
        side = Path(str(TARGET) + ext)
        if side.is_file():
            try:
                side.unlink()
            except OSError as exc:
                print(f"Warning: could not remove {side.name}: {exc}")
    shutil.copy2(SOURCE, TARGET)
    conn = sqlite3.connect(TARGET)
    ok = conn.execute("PRAGMA quick_check").fetchone()[0]
    conn.close()
    print(f"Restored {TARGET} — quick_check={ok}")
    return 0 if ok == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
