# -*- coding: utf-8 -*-
"""Hybrid autonomy — queue sensitive writes for owner approval."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from typing import Any, Callable, Dict, Optional

from app.office_ai.tools import update_csv as update_csv_tool


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def requires_approval(tool_name: str) -> bool:
    from pathlib import Path
    import json as _json

    for cfg_path in (
        Path(__file__).resolve().parent / "ai_viability_matrix.json",
        Path(__file__).resolve().parent / "office_ai_sources.json",
    ):
        if cfg_path.is_file():
            cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
            required = cfg.get("approval_required_tools", [])
            if tool_name in required:
                return True
            auto = cfg.get("auto_execute_tools", [])
            if tool_name in auto:
                return False
    return tool_name in {"update_financial_csv", "run_workspace_sync", "generate_customer_pdf"}


def queue_action(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    user_id: int,
    username: str,
    tool_name: str,
    args: Dict[str, Any],
    preview_text: str,
) -> int:
    cur = conn.execute(
        """INSERT INTO office_ai_pending_actions
           (session_id, user_id, username, tool_name, args_json, preview_text, status, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (session_id, user_id, username, tool_name, json.dumps(args), preview_text, "Pending", _now()),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_pending(conn: sqlite3.Connection) -> list:
    rows = conn.execute(
        "SELECT * FROM office_ai_pending_actions WHERE status='Pending' ORDER BY id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_action(conn: sqlite3.Connection, action_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM office_ai_pending_actions WHERE id=?", (action_id,)).fetchone()
    return dict(row) if row else None


def approve_action(conn: sqlite3.Connection, action_id: int, decided_by: str) -> dict:
    row = get_action(conn, action_id)
    if not row:
        return {"ok": False, "error": "Action not found"}
    if row["status"] != "Pending":
        return {"ok": False, "error": f"Action already {row['status']}"}
    args = json.loads(row["args_json"] or "{}")
    tool_name = row["tool_name"]
    result = _execute_tool(tool_name, args)
    status = "Approved" if result.get("ok") else "Failed"
    if result.get("ok"):
        try:
            from app.office_ai.learning_store import record_approved_action

            record_approved_action(
                conn,
                tool_name=tool_name,
                args=args,
                preview_text=row.get("preview_text") or "",
                approved_by=decided_by,
            )
        except Exception:
            pass
    conn.execute(
        """UPDATE office_ai_pending_actions SET status=?, decided_by=?, decided_at=?, decision_note=?
           WHERE id=?""",
        (status, decided_by, _now(), result.get("message") or result.get("error", ""), action_id),
    )
    conn.commit()
    return result


def deny_action(conn: sqlite3.Connection, action_id: int, decided_by: str, note: str = "") -> dict:
    conn.execute(
        """UPDATE office_ai_pending_actions SET status='Denied', decided_by=?, decided_at=?, decision_note=?
           WHERE id=? AND status='Pending'""",
        (decided_by, _now(), note or "Denied by owner", action_id),
    )
    conn.commit()
    return {"ok": True, "message": "Denied"}


def _execute_tool(tool_name: str, args: Dict[str, Any]) -> dict:
    from app.office_ai.tools import generate_customer_pdf, run_workspace_sync, update_csv as update_csv_tool
    from app.office_ai.tools import quote_build_quote_package

    if tool_name == "update_financial_csv":
        return update_csv_tool.execute(**args)
    if tool_name == "run_workspace_sync":
        return run_workspace_sync.execute(**args)
    if tool_name == "generate_customer_pdf":
        return generate_customer_pdf.execute(**args)
    if tool_name == "build_quote_package":
        return quote_build_quote_package.run(**args)
    return {"ok": False, "error": f"No executor for {tool_name}"}
