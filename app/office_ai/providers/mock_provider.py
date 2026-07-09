# -*- coding: utf-8 -*-
"""Mock provider for offline verification and tests."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.office_ai.providers.base import LLMResponse, ToolCall


class MockProvider:
    name = "mock"

    def __init__(self, model: str = "mock-local") -> None:
        self.model = model

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        *,
        stream: bool = False,
    ) -> LLMResponse:
        last = messages[-1].get("content", "") if messages else ""
        lower = (last or "").lower()
        if "test connection" in lower:
            return LLMResponse(content="OK", provider=self.name, model=self.model)
        if "dashboard" in lower or "open" in lower or "lily" in lower:
            return LLMResponse(
                content="I'll read the business dashboard for you.",
                tool_calls=[ToolCall(id="mock1", name="read_dashboard", arguments={})],
                provider=self.name,
                model=self.model,
            )
        if "log" in lower or "helper" in lower or "pay" in lower:
            return LLMResponse(
                content="I'll add a daily log note. Payroll CSV will need your approval.",
                tool_calls=[
                    ToolCall(
                        id="mock2",
                        name="append_daily_log",
                        arguments={"note": last[:500]},
                    )
                ],
                provider=self.name,
                model=self.model,
            )
        return LLMResponse(
            content=(
                "Office AI mock mode (no API key). Configure OpenAI at /ai. "
                f"You said: {(last or '')[:200]}"
            ),
            provider=self.name,
            model=self.model,
        )

    def test_connection(self) -> tuple[bool, str]:
        return True, "Mock provider OK"
