# -*- coding: utf-8 -*-
"""J & R Construction Manager — in-app Office AI."""

from app.office_ai.orchestrator import OfficeAIOrchestrator
from app.office_ai.schema import ensure_office_ai_schema

__all__ = ["OfficeAIOrchestrator", "ensure_office_ai_schema"]
