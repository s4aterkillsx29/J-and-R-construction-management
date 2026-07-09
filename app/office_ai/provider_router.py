# -*- coding: utf-8 -*-
"""Pick LLM provider from app settings."""
from __future__ import annotations

import os
import sqlite3

from app.office_ai.config import get_provider_api_key, get_setting
from app.office_ai.providers.anthropic_provider import AnthropicProvider
from app.office_ai.providers.gemini_provider import GeminiProvider
from app.office_ai.providers.groq_provider import GroqProvider
from app.office_ai.providers.mock_provider import MockProvider
from app.office_ai.providers.ollama_provider import OllamaProvider
from app.office_ai.providers.openai_provider import OpenAIProvider


def get_provider(conn: sqlite3.Connection, provider_name: str | None = None, model: str | None = None):
    name = (provider_name or get_setting(conn, "office_ai_default_provider", "groq")).strip().lower()
    mdl = model or get_setting(conn, "office_ai_model", "")

    if name == "openai":
        key = get_provider_api_key(conn, "openai")
        if key:
            return OpenAIProvider(key, model=mdl or "gpt-4o")
        return MockProvider(model="mock-no-openai-key")

    if name == "groq":
        key = get_provider_api_key(conn, "groq")
        if key:
            return GroqProvider(key, model=mdl or "llama-3.3-70b-versatile")
        return MockProvider(model="mock-no-groq-key")

    if name == "gemini":
        key = get_provider_api_key(conn, "gemini")
        if key:
            return GeminiProvider(key, model=mdl or "gemini-2.0-flash")
        return MockProvider(model="mock-no-gemini-key")

    if name == "anthropic":
        key = get_provider_api_key(conn, "anthropic")
        if key:
            return AnthropicProvider(key, model=mdl or "claude-3-5-haiku-20241022")
        return MockProvider(model="mock-no-anthropic-key")

    if name == "ollama":
        base = get_setting(conn, "office_ai_ollama_url", os.environ.get("JRC_OLLAMA_URL", "http://127.0.0.1:11434/v1"))
        return OllamaProvider(api_key="ollama", model=mdl or "llama3.2", base_url=base)

    if name == "mock":
        return MockProvider(model=mdl or "mock-local")

    return MockProvider(model=f"unsupported-{name}")
