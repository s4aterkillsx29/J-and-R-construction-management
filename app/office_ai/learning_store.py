# -*- coding: utf-8 -*-
"""Phase 5 — learn from owner-approved actions (few-shot examples)."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from typing import List, Optional


def ensure_learning_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS office_ai_learning_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT NOT NULL,
            summary TEXT NOT NULL,
            args_json TEXT,
            approved_by TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()


def record_approved_action(
    conn: sqlite3.Connection,
    *,
    tool_name: str,
    args: dict,
    preview_text: str,
    approved_by: str,
) -> None:
    ensure_learning_schema(conn)
    summary = (preview_text or "")[:2000]
    conn.execute(
        """INSERT INTO office_ai_learning_examples (tool_name, summary, args_json, approved_by, created_at)
           VALUES (?,?,?,?,?)""",
        (
            tool_name,
            summary,
            json.dumps(args)[:8000],
            approved_by,
            dt.datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    # Keep table bounded
    conn.execute(
        """DELETE FROM office_ai_learning_examples WHERE id NOT IN (
            SELECT id FROM office_ai_learning_examples ORDER BY id DESC LIMIT 200
        )"""
    )
    conn.commit()


def load_learning_context(conn: sqlite3.Connection, *, limit: int = 12) -> str:
    ensure_learning_schema(conn)
    rows = conn.execute(
        "SELECT tool_name, summary, approved_by, created_at FROM office_ai_learning_examples ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    if not rows:
        return ""
    lines = ["## Owner-approved examples (follow these patterns)"]
    for r in rows:
        lines.append(
            f"- [{r[3]}] {r[0]} (by {r[2]}): {(r[1] or '')[:400]}"
        )
    return "\n".join(lines)
