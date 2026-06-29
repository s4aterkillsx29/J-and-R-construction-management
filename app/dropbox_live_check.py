"""Dropbox live readiness check — run before go-live."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
EXPORT = BASE / "exports"
DATA = Path(__import__("os").environ.get("JRC_DATA_DIR", str(BASE / "data")))


def main() -> int:
    db_path = DATA / "jr_business.db"
    if not db_path.exists():
        print("WARN: No business database yet — Dropbox check partial only.")
        conn = sqlite3.connect(":memory:")
    else:
        conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
    from app.dropbox_business import run_dropbox_live_check

    report = run_dropbox_live_check(conn)
    EXPORT.mkdir(parents=True, exist_ok=True)
    out = EXPORT / "JRC_Dropbox_Live_Check.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    for c in report.get("checks", []):
        print(f"[{c['level']}] {c['name']}: {c['detail']}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
