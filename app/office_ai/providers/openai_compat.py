# -*- coding: utf-8 -*-
"""OpenAI-compatible chat API (Groq, Ollama, OpenRouter, etc.)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from app.office_ai.providers.base import LLMResponse, ToolCall


class OpenAICompatProvider:
    """HTTP client for /v1/chat/completions compatible APIs."""

    def __init__(
        self,
        *,
        name: str,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float = 90.0,
    ) -> None:
        self.name = name
        self.api_key = api_key or ""
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        *,
        stream: bool = False,
    ) -> LLMResponse:
        if not self.api_key and "11434" not in self.base_url:
            return LLMResponse(
                error=f"{self.name} API key not configured. Add it at /ai settings.",
                provider=self.name,
                model=self.model,
            )
        body: Dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        data = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:500]
            return LLMResponse(
                error=f"{self.name} HTTP {exc.code}: {detail}",
                provider=self.name,
                model=self.model,
            )
        except Exception as exc:
            return LLMResponse(error=str(exc), provider=self.name, model=self.model)

        choice = payload["choices"][0]["message"]
        tool_calls: List[ToolCall] = []
        for tc in choice.get("tool_calls") or []:
            fn = tc.get("function", {})
            args: Dict[str, Any] = {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                pass
            tool_calls.append(ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args))
        usage = payload.get("usage") or {}
        return LLMResponse(
            content=choice.get("content") or "",
            tool_calls=tool_calls,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            provider=self.name,
            model=self.model,
        )

    def test_connection(self) -> tuple[bool, str]:
        resp = self.complete([{"role": "user", "content": "Reply with exactly: OK"}])
        if resp.error:
            return False, resp.error
        return True, (resp.content or "OK")[:120]
