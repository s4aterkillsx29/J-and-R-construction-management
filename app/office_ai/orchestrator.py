# -*- coding: utf-8 -*-
"""Office AI chat orchestrator."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.office_ai import context_loader, tool_registry
from app.office_ai.config import get_setting, office_ai_config
from app.office_ai.provider_fallback import complete_with_fallback


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


class OfficeAIOrchestrator:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _system_prompt(self) -> str:
        prompt_path = Path(__file__).resolve().parent / "prompts" / "system.txt"
        try:
            base = prompt_path.read_text(encoding="utf-8") if prompt_path.is_file() else ""
        except Exception:
            base = "You are the J & R Construction Office Assistant."
        try:
            ctx = context_loader.load_context(tiers=["core", "session"], max_total_chars=32000)
        except Exception as exc:
            ctx = f"(Context load warning: {exc})"
        try:
            from app.office_ai.learning_store import load_learning_context

            learn = load_learning_context(self.conn, limit=10)
            if learn:
                ctx = ctx + "\n\n" + learn
        except Exception:
            pass
        combined = f"{base}\n\n## Office context\n{ctx}"
        if len(combined) > 48000:
            combined = combined[:48000] + "\n\n[Context truncated for model limits]"
        return combined

    def get_or_create_session(self, user_id: int, username: str, session_id: Optional[int] = None) -> int:
        if session_id:
            row = self.conn.execute(
                "SELECT id FROM office_ai_sessions WHERE id=? AND user_id=?",
                (session_id, user_id),
            ).fetchone()
            if row:
                return int(row[0])
        cfg = office_ai_config(self.conn)
        cur = self.conn.execute(
            """INSERT INTO office_ai_sessions (user_id, username, title, provider, model, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                user_id,
                username,
                "Office chat",
                cfg["default_provider"],
                cfg["default_model"],
                _now(),
                _now(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def _history(self, session_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT role, content, tool_calls_json FROM office_ai_messages
               WHERE session_id=? ORDER BY id DESC LIMIT ?""",
            (session_id, limit),
        ).fetchall()
        messages: List[Dict[str, Any]] = []
        for row in reversed(rows):
            msg: Dict[str, Any] = {"role": row[0], "content": row[1] or ""}
            if row[2]:
                try:
                    msg["tool_calls"] = json.loads(row[2])
                except Exception:
                    pass
            messages.append(msg)
        return messages

    def _save_message(self, session_id: int, role: str, content: str, tool_calls_json: str = "") -> None:
        self.conn.execute(
            """INSERT INTO office_ai_messages (session_id, role, content, tool_calls_json, created_at)
               VALUES (?,?,?,?,?)""",
            (session_id, role, content, tool_calls_json or None, _now()),
        )
        self.conn.execute(
            "UPDATE office_ai_sessions SET updated_at=? WHERE id=?",
            (_now(), session_id),
        )
        self.conn.commit()

    def _log_usage(self, user_id: int, username: str, provider: str, model: str, prompt_t: int, comp_t: int) -> None:
        self.conn.execute(
            """INSERT INTO office_ai_usage_log
               (user_id, username, provider, model, prompt_tokens, completion_tokens, cost_estimate, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (user_id, username, provider, model, prompt_t, comp_t, 0.0, _now()),
        )
        self.conn.commit()

    def chat(
        self,
        *,
        user_id: int,
        username: str,
        message: str,
        session_id: Optional[int] = None,
    ) -> dict:
        sid: Optional[int] = None
        try:
            if get_setting(self.conn, "office_ai_enabled", "1") != "1":
                return {"ok": False, "error": "Office AI is disabled in settings. Enable at /ai."}

            if not (message or "").strip():
                return {"ok": False, "error": "Message is empty."}

            sid = self.get_or_create_session(user_id, username, session_id)
            self._save_message(sid, "user", message.strip())

            provider_name = get_setting(self.conn, "office_ai_default_provider", "groq")
            model = get_setting(self.conn, "office_ai_model", "llama-3.3-70b-versatile")
            use_fallback = get_setting(self.conn, "office_ai_use_fallback", "1") == "1"

            messages: List[Dict[str, Any]] = [{"role": "system", "content": self._system_prompt()}]
            messages.extend(self._history(sid))
            messages.append({"role": "user", "content": message.strip()})

            if use_fallback:
                resp = complete_with_fallback(self.conn, messages, tools=tool_registry.tool_schemas())
            else:
                from app.office_ai.provider_router import get_provider

                provider = get_provider(self.conn, provider_name, model)
                resp = provider.complete(messages, tools=tool_registry.tool_schemas())
            if resp.error:
                err_text = f"Could not reach AI provider: {resp.error}"
                if "api key" in resp.error.lower() or "401" in resp.error:
                    err_text += " Add or update your key at /ai, or use Mock provider for offline testing."
                self._save_message(sid, "assistant", err_text)
                return {"ok": False, "error": err_text, "session_id": sid}

            self._log_usage(
                user_id, username, resp.provider or provider_name, resp.model or model,
                resp.prompt_tokens, resp.completion_tokens,
            )

            tool_results: List[dict] = []
            assistant_text = (resp.content or "").strip()

            if resp.tool_calls:
                for tc in resp.tool_calls:
                    try:
                        result = tool_registry.run_tool(
                            tc.name,
                            tc.arguments or {},
                            conn=self.conn,
                            session_id=sid,
                            user_id=user_id,
                            username=username,
                        )
                    except Exception as exc:
                        result = {"ok": False, "error": f"{tc.name} failed: {exc}"}
                    tool_results.append({"tool": tc.name, "result": result})
                    if result.get("pending_approval"):
                        assistant_text += (
                            f"\n\nPending approval (#{result.get('pending_approval_id')}): "
                            f"{result.get('message', 'Review at /office-ai/approvals')}"
                        )
                    elif result.get("ok"):
                        if result.get("content"):
                            assistant_text += f"\n\n[{tc.name}] {str(result.get('content'))[:1500]}"
                        elif result.get("message"):
                            assistant_text += f"\n\nDone: {result.get('message')}"
                    else:
                        assistant_text += f"\n\nWarning — {tc.name}: {result.get('error', 'failed')}"

                self._save_message(
                    sid, "assistant", assistant_text or "(Tools ran; see details above.)",
                    json.dumps([tc.__dict__ for tc in resp.tool_calls]),
                )
            else:
                if not assistant_text:
                    assistant_text = "No response from the model. Try again or check /ai settings."
                self._save_message(sid, "assistant", assistant_text)

            pending = [r for r in tool_results if r["result"].get("pending_approval")]
            return {
                "ok": True,
                "session_id": sid,
                "reply": assistant_text,
                "tool_results": tool_results,
                "pending_approvals": [r["result"].get("pending_approval_id") for r in pending],
                "provider": resp.provider or provider_name,
                "model": resp.model or model,
            }
        except Exception as exc:
            err = f"Office AI error: {type(exc).__name__}: {exc}"
            if sid:
                try:
                    self._save_message(sid, "assistant", err)
                except Exception:
                    pass
            return {"ok": False, "error": err, "session_id": sid}
