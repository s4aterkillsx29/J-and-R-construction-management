"""Stripe Checkout end-to-end helpers."""
from __future__ import annotations

import json
import os
import sqlite3
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple


def stripe_configured() -> bool:
    return bool(os.environ.get("STRIPE_SECRET_KEY", "").strip())


def create_checkout_session(
    request_code: str,
    total_cents: int,
    username: str,
    success_base: str,
) -> Tuple[bool, str, str]:
    """Returns ok, checkout_url, session_id."""
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key:
        return False, "", ""
    success = f"{success_base.rstrip('/')}?code={urllib.parse.quote(request_code)}&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_base = success_base.rstrip("/")
    if cancel_base.endswith("/payments/complete"):
        cancel_base = cancel_base[: -len("/payments/complete")] + "/payments/cancel"
    else:
        cancel_base = cancel_base + "/payments/cancel"
    cancel = f"{cancel_base}?code={urllib.parse.quote(request_code)}"
    data = urllib.parse.urlencode({
        "mode": "payment",
        "success_url": success,
        "cancel_url": cancel,
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][product_data][name]": f"JRC Payment {request_code}",
        "line_items[0][price_data][unit_amount]": str(int(total_cents)),
        "line_items[0][quantity]": "1",
        "metadata[request_code]": request_code,
        "metadata[username]": username,
    }).encode()
    req = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            payload = json.loads(resp.read().decode())
            return True, payload.get("url", ""), payload.get("id", "")
    except Exception as exc:
        return False, str(exc), ""


def retrieve_checkout_session(session_id: str) -> Optional[Dict[str, Any]]:
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key or not session_id:
        return None
    req = urllib.request.Request(
        f"https://api.stripe.com/v1/checkout/sessions/{urllib.parse.quote(session_id)}",
        headers={"Authorization": f"Bearer {key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def handle_checkout_completed(conn: sqlite3.Connection, request_code: str, confirmed_by: str = "stripe") -> Tuple[bool, str]:
    from app.payment_system import confirm_payment
    row = conn.execute(
        "SELECT id FROM debit_payment_requests WHERE request_code=? LIMIT 1", (request_code,)
    ).fetchone()
    if not row:
        return False, "Payment request not found."
    return confirm_payment(conn, int(row["id"]), confirmed_by)


def verify_webhook_signature(payload: bytes, sig_header: str) -> bool:
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret:
        return False
    import hashlib
    import hmac
    import time
    parts = {}
    for item in sig_header.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            parts[k.strip()] = v.strip()
    ts = parts.get("t", "")
    v1 = parts.get("v1", "")
    if not ts or not v1:
        return False
    try:
        if abs(int(time.time()) - int(ts)) > 300:
            return False
    except Exception:
        return False
    signed = f"{ts}.{payload.decode('utf-8')}".encode()
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)
