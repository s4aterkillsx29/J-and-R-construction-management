# -*- coding: utf-8 -*-
"""Anthropic Claude API."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from app.office_ai.providers.base import LLMResponse, ToolCall

DEFAULT_MODEL = "claude-3-5-haiku-20241022"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        *,
        stream: bool = False,
    ) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                error="Anthropic API key not configured. Add at /ai settings.",
                provider=self.name,
                model=self.model,
            )
        system = ""
        api_messages: list = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                system += (msg.get("content") or "") + "\n"
            else:
                api_messages.append({"role": role, "content": msg.get("content") or ""})

        body: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": api_messages,
        }
        if system.strip():
            body["system"] = system.strip()

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=data,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:500]
            return LLMResponse(error=f"Anthropic HTTP {exc.code}: {detail}", provider=self.name, model=self.model)
        except Exception as exc:
            return LLMResponse(error=str(exc), provider=self.name, model=self.model)

        blocks = payload.get("content") or []
        text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        usage = payload.get("usage") or {}
        return LLMResponse(
            content=text,
            prompt_tokens=int(usage.get("input_tokens") or 0),
            completion_tokens=int(usage.get("output_tokens") or 0),
            provider=self.name,
            model=self.model,
        )

    def test_connection(self) -> tuple[bool, str]:
        resp = self.complete([{"role": "user", "content": "Reply with exactly: OK"}])
        if resp.error:
            return False, resp.error
        return True, (resp.content or "OK")[:120]
