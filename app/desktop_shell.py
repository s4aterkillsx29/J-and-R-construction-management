# -*- coding: utf-8 -*-
"""Embedded pywebview desktop shell — web UI in native window with SSO."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import quote

BASE_DIR = Path(__file__).resolve().parents[1]
APP_NAME = "J and R Construction Manager"


def prefers_embedded() -> bool:
    return os.environ.get("JRC_USE_EMBEDDED_WEB", "1").strip().lower() not in ("0", "false", "no")


def build_sso_url(port: int, user: Dict[str, Any], path: str = "/") -> str:
    from app.desktop_sso import mint_desktop_sso_token

    token = mint_desktop_sso_token(int(user["id"]), str(user["username"]))
    dest = path if path.startswith("/") else "/" + path
    if dest in ("/login", "", "/setup-complete"):
        dest = "/"
    return f"http://127.0.0.1:{int(port)}/auth/desktop-bridge?token={quote(token)}&next={quote(dest)}"


def run_embedded_desktop(base_dir: Path, user: Dict[str, Any]) -> bool:
    """Launch embedded webview main window. Returns False to fallback to Start Center."""
    if not prefers_embedded():
        return False
    try:
        import webview  # noqa: F401
    except ImportError:
        return False

    from app.server_control import start_if_needed

    status = start_if_needed(base_dir)
    port = int(status.get("port") or 8765)
    if not status.get("running") and not status.get("started"):
        return False

    url = build_sso_url(port, user, "/")
    try:
        import webview

        window = webview.create_window(
            APP_NAME,
            url,
            width=1280,
            height=860,
            min_size=(640, 480),
            text_select=True,
        )

        def on_closed():
            try:
                from app.desktop_session import revoke_desktop_session

                revoke_desktop_session(base_dir, "Embedded shell closed")
            except Exception:
                pass

        window.events.closed += on_closed
        webview.start()
        return True
    except Exception:
        return False


def open_embedded_path(base_dir: Path, user: Dict[str, Any], path: str = "/") -> bool:
    """Open a path in embedded webview (blocks until window closed)."""
    if not prefers_embedded():
        return False
    try:
        import webview
    except ImportError:
        return False

    from app.server_control import start_if_needed

    status = start_if_needed(base_dir)
    port = int(status.get("port") or 8765)
    url = build_sso_url(port, user, path)
    try:
        webview.create_window(APP_NAME, url, width=1280, height=860, min_size=(640, 480))
        webview.start()
        return True
    except Exception:
        return False
