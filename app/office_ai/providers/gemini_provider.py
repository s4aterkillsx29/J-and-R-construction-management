# -*- coding: utf-8 -*-
"""Google Gemini — free tier API."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from app.office_ai.providers.base import LLMResponse, ToolCall

DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL

    def _to_gemini_messages(self, messages: List[Dict[str, Any]]) -> tuple[str, list]:
        system = ""
        contents: list = []
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content") or ""
            if role == "system":
                system += text + "\n"
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": text}]})
            else:
                contents.append({"role": "user", "parts": [{"text": text}]})
        return system.strip(), contents

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        *,
        stream: bool = False,
    ) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                error="Gemini API key not configured. Get a free key at Google AI Studio, then add at /ai.",
                provider=self.name,
                model=self.model,
            )
        system, contents = self._to_gemini_messages(messages)
        body: Dict[str, Any] = {"contents": contents}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:500]
            return LLMResponse(error=f"Gemini HTTP {exc.code}: {detail}", provider=self.name, model=self.model)
        except Exception as exc:
            return LLMResponse(error=str(exc), provider=self.name, model=self.model)

        candidates = payload.get("candidates") or []
        if not candidates:
            return LLMResponse(error="Gemini returned no candidates", provider=self.name, model=self.model)
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "\n".join(p.get("text", "") for p in parts if p.get("text"))
        usage = payload.get("usageMetadata") or {}
        return LLMResponse(
            content=text,
            prompt_tokens=int(usage.get("promptTokenCount") or 0),
            completion_tokens=int(usage.get("candidatesTokenCount") or 0),
            provider=self.name,
            model=self.model,
        )

    def test_connection(self) -> tuple[bool, str]:
        resp = self.complete([{"role": "user", "content": "Reply with exactly: OK"}])
        if resp.error:
            return False, resp.error
        return True, (resp.content or "OK")[:120]
