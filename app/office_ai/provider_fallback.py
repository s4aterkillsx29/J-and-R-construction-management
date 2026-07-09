# -*- coding: utf-8 -*-
"""Phase 6 — try configured provider, then safe fallbacks."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from app.office_ai.config import get_provider_api_key, get_setting
from app.office_ai.provider_router import get_provider
from app.office_ai.providers.base import LLMResponse


def fallback_chain(conn: sqlite3.Connection) -> List[str]:
    primary = get_setting(conn, "office_ai_default_provider", "groq").strip().lower()
    configured = get_setting(conn, "office_ai_fallback_chain", "groq,gemini,ollama,openai,mock")
    chain = [p.strip().lower() for p in configured.split(",") if p.strip()]
    if primary and primary not in chain:
        chain.insert(0, primary)
    elif primary:
        chain = [primary] + [p for p in chain if p != primary]
    # Only include providers with keys (except ollama/mock)
    out: List[str] = []
    for name in chain:
        if name in ("mock", "ollama"):
            out.append(name)
        elif get_provider_api_key(conn, name):
            out.append(name)
    if "mock" not in out:
        out.append("mock")
    return out


def complete_with_fallback(
    conn: sqlite3.Connection,
    messages: List[Dict[str, Any]],
    tools: Optional[List[dict]] = None,
) -> LLMResponse:
    errors: List[str] = []
    for name in fallback_chain(conn):
        # Empty model — each provider uses its own default (see provider_router).
        provider = get_provider(conn, name, "")
        resp = provider.complete(messages, tools=tools)
        if not resp.error:
            return resp
        errors.append(f"{name}: {resp.error[:120]}")
    return LLMResponse(
        error="All providers failed. " + " | ".join(errors[:4]),
        provider="fallback",
        model="",
    )
