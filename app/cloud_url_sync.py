"""Keep cloud_connect.json and app_settings remote URL in sync."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
CLOUD_CONNECT_PATH = BASE_DIR / "data" / "cloud_connect.json"
DB_PATH = BASE_DIR / "data" / "jr_business.db"


def normalize_base_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if value and not value.startswith(("http://", "https://")):
        value = "https://" + value
    return value


def sync_cloud_url(url: str) -> str:
    url = normalize_base_url(url)
    CLOUD_CONNECT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cloud_base_url": url,
        "updated_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": "Synced between Start Center and network server for mobile/cloud links.",
    }
    CLOUD_CONNECT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if DB_PATH.exists():
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)"
                )
                conn.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                    ("remote_public_base_url", url),
                )
                conn.commit()
        except Exception:
            pass
    return url
