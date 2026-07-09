# -*- coding: utf-8 -*-
"""Office AI access — owner/admin only."""
from __future__ import annotations

from typing import Any, Optional

from app.role_utils import is_admin_role, normalize_role


def is_office_ai_user(user: Any) -> bool:
    """Office AI is restricted to owner/admin accounts only."""
    if not user:
        return False
    role = normalize_role(user.get("role") if isinstance(user, dict) else getattr(user, "role", ""))
    if not is_admin_role(role):
        return False
    if isinstance(user, dict) and not int(user.get("active") or 1):
        return False
    return True


def office_ai_access_message() -> str:
    return "Office AI is available to owner/admin accounts only."
