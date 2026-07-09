# -*- coding: utf-8 -*-
"""Ollama — local free models (OpenAI-compatible)."""
from __future__ import annotations

import os

from app.office_ai.providers.openai_compat import OpenAICompatProvider

DEFAULT_MODEL = "llama3.2"
DEFAULT_BASE = os.environ.get("JRC_OLLAMA_URL", "http://127.0.0.1:11434/v1")


class OllamaProvider(OpenAICompatProvider):
    name = "ollama"

    def __init__(self, api_key: str = "ollama", model: str = DEFAULT_MODEL, base_url: str = DEFAULT_BASE) -> None:
        super().__init__(
            name="ollama",
            api_key=api_key or "ollama",
            model=model or DEFAULT_MODEL,
            base_url=base_url or DEFAULT_BASE,
            timeout=120.0,
        )
