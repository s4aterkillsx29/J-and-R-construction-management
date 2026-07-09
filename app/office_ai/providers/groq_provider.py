# -*- coding: utf-8 -*-
"""Groq — fast free-tier LLM (OpenAI-compatible)."""
from __future__ import annotations

from app.office_ai.providers.openai_compat import OpenAICompatProvider

DEFAULT_MODEL = "llama-3.3-70b-versatile"
BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(OpenAICompatProvider):
    name = "groq"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        super().__init__(name="groq", api_key=api_key, model=model or DEFAULT_MODEL, base_url=BASE_URL)
