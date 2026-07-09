# -*- coding: utf-8 -*-
"""Office AI settings and encrypted API key storage."""
from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
from typing import Callable, Optional


def _machine_salt(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key='office_ai_key_salt'").fetchone()
    if row and row[0]:
        return str(row[0])
    salt = base64.urlsafe_b64encode(os.urandom(24)).decode("ascii")
    conn.execute(
        "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
        ("office_ai_key_salt", salt),
    )
    conn.commit()
    return salt


def _derive_key(salt: str) -> bytes:
    seed = (salt + "|jrc-office-ai-v1").encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", seed, b"jrc-office-ai", 120000)


def encrypt_secret(conn: sqlite3.Connection, plain: str) -> str:
    if not plain:
        return ""
    salt = _machine_salt(conn)
    key = _derive_key(salt)
    data = plain.encode("utf-8")
    xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return "enc1:" + base64.urlsafe_b64encode(xored).decode("ascii")


def decrypt_secret(conn: sqlite3.Connection, stored: str) -> str:
    if not stored:
        return ""
    if not stored.startswith("enc1:"):
        return stored
    salt = _machine_salt(conn)
    key = _derive_key(salt)
    raw = base64.urlsafe_b64decode(stored[5:].encode("ascii"))
    plain = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    return plain.decode("utf-8", errors="ignore")


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    try:
        row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return row[0] if row and row[0] is not None else default
    except Exception:
        return default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, value or ""))
    conn.commit()


def get_provider_api_key(conn: sqlite3.Connection, provider: str) -> str:
    raw = get_setting(conn, f"office_ai_api_key_{provider}", "")
    return decrypt_secret(conn, raw)


def set_provider_api_key(conn: sqlite3.Connection, provider: str, api_key: str) -> None:
    set_setting(conn, f"office_ai_api_key_{provider}", encrypt_secret(conn, api_key.strip()))


def office_ai_config(conn: sqlite3.Connection) -> dict:
    return {
        "default_provider": get_setting(conn, "office_ai_default_provider", "groq"),
        "default_model": get_setting(conn, "office_ai_model", "llama-3.3-70b-versatile"),
        "enabled": get_setting(conn, "office_ai_enabled", "1") == "1",
        "fallback_chain": get_setting(conn, "office_ai_fallback_chain", "groq,gemini,ollama,openai,mock"),
        "openai_configured": bool(get_provider_api_key(conn, "openai")),
        "groq_configured": bool(get_provider_api_key(conn, "groq")),
        "gemini_configured": bool(get_provider_api_key(conn, "gemini")),
        "anthropic_configured": bool(get_provider_api_key(conn, "anthropic")),
        "ollama_url": get_setting(conn, "office_ai_ollama_url", "http://127.0.0.1:11434/v1"),
    }


PROVIDER_MODEL_DEFAULTS = {
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-2.0-flash",
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-haiku-20241022",
    "ollama": "llama3.2",
    "mock": "mock-local",
}
