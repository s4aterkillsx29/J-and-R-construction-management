# -*- coding: utf-8 -*-
"""Global login gate — every user (including admin) must sign in before program use."""
from __future__ import annotations

import platform
from typing import Optional, Set, Tuple

PUBLIC_EXACT = frozenset({
    "/login",
    "/logout",
    "/register",
    "/account-request",
    "/apply",
    "/emergency-access",
    "/auth/desktop-bridge",
    "/mobile/ping",
    "/connect",
    "/payments/complete",
    "/payments/cancel",
    "/payments/stripe/webhook",
})

PUBLIC_PREFIXES = (
    "/static/",
    "/apply/thanks/",
    "/apply/status/",
)

PUBLIC_API = frozenset({
    "/api/health",
    "/api/connection",
    "/api/cloud/status",
    "/api/cloud/primary-status",
    "/api/live/ready",
})


def is_public_path(path: str) -> bool:
    if not path:
        return True
    if path in PUBLIC_EXACT or path in PUBLIC_API:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


def enforce_web_login_gate(session: dict, redirect_login) -> Optional[object]:
    """Return a Flask redirect response if the request must login first."""
    from flask import request

    path = request.path or ""
    if is_public_path(path):
        return None
    if path == "/login-start":
        return redirect_login("/login")
    if not session.get("user_id"):
        nxt = path
        if request.query_string:
            nxt = f"{path}?{request.query_string.decode('utf-8', errors='ignore')}"
        return redirect_login(nxt)
    return None


def pc_identity() -> Tuple[str, str]:
    """Return (hostname, platform) for trusted-PC verification display."""
    return platform.node() or "unknown", platform.platform()


def record_pc_verification(conn, user_id: int, username: str, ip: str, ua: str) -> str:
    """Log PC-rooted login verification for security audit."""
    host, plat = pc_identity()
    msg = f"PC verified: {host} | {plat} | IP {ip}"
    try:
        conn.execute(
            """INSERT INTO security_events (event_time, level, event_type, username, ip_address, user_agent, message)
               VALUES (datetime('now','localtime'), 'OK', 'pc_login_verified', ?, ?, ?, ?)""",
            (username, ip, ua[:200] if ua else "", msg),
        )
        conn.commit()
    except Exception:
        pass
    return host
