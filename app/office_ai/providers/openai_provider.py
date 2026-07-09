# -*- coding: utf-8 -*-
"""OpenAI Chat Completions provider."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.office_ai.providers.base import LLMResponse, ToolCall


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        self.api_key = api_key
        self.model = model

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        *,
        stream: bool = False,
    ) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                error="OpenAI API key not configured. Add it at /ai settings.",
                provider=self.name,
                model=self.model,
            )
        try:
            from openai import OpenAI
        except ImportError:
            return self._complete_httpx(messages, tools)

        client = OpenAI(api_key=self.api_key)
        kwargs: Dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception as exc:
            return LLMResponse(error=str(exc), provider=self.name, model=self.model)

        choice = resp.choices[0].message
        tool_calls: List[ToolCall] = []
        if choice.tool_calls:
            for tc in choice.tool_calls:
                args = {}
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    pass
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        usage = getattr(resp, "usage", None)
        return LLMResponse(
            content=choice.content or "",
            tool_calls=tool_calls,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            provider=self.name,
            model=self.model,
        )

    def _complete_httpx(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
    ) -> LLMResponse:
        import urllib.error
        import urllib.request

        body: Dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:500]
            return LLMResponse(error=f"OpenAI HTTP {exc.code}: {detail}", provider=self.name, model=self.model)
        except Exception as exc:
            return LLMResponse(error=str(exc), provider=self.name, model=self.model)

        choice = payload["choices"][0]["message"]
        tool_calls: List[ToolCall] = []
        for tc in choice.get("tool_calls") or []:
            fn = tc.get("function", {})
            args = {}
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
