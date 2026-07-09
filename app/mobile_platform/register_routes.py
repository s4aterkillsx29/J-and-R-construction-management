# -*- coding: utf-8 -*-
"""Mobile outbox API + status."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from flask import jsonify, request

from app.mobile_platform.outbox_schema import ensure_outbox_schema


def register_mobile_platform_routes(
    app,
    *,
    db_fn: Callable,
    login_required: Callable,
    current_user: Callable,
    base_dir: Path,
) -> None:
    temp_dir = base_dir / "data" / "mobile_outbox_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    @app.route("/api/mobile/outbox/batch", methods=["POST"])
    @login_required()
    def api_mobile_outbox_batch():
        user = current_user()
        conn = db_fn()
        ensure_outbox_schema(conn)
        items = request.json if request.is_json else {}
        batch = items.get("items") or []
        ids = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in batch:
            client_id = item.get("client_id") or str(uuid.uuid4())
            cur = conn.execute(
                """INSERT INTO mobile_outbox (client_id, username, event_type, job_code, payload_json, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    client_id,
                    user.get("username", ""),
                    item.get("event_type", "note"),
                    item.get("job_code", ""),
                    json.dumps(item.get("payload") or {}),
                    now,
                ),
            )
            oid = int(cur.lastrowid)
            ids.append({"client_id": client_id, "server_id": oid})
        conn.commit()
        return jsonify({"ok": True, "accepted": ids})

    @app.route("/api/mobile/status")
    @login_required()
    def api_mobile_status():
        conn = db_fn()
        ensure_outbox_schema(conn)
        pending = conn.execute(
            "SELECT COUNT(*) FROM mobile_outbox WHERE status='pending'"
        ).fetchone()[0]
        return jsonify({"ok": True, "online": True, "outbox_pending": pending})
