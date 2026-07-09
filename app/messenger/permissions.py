# -*- coding: utf-8 -*-
"""Role → channel permissions for messenger."""
from __future__ import annotations

from typing import Set

ROLE_CHANNELS: dict[str, Set[str]] = {
    "admin": {"team", "job", "dm", "admin_broadcast", "announcement"},
    "manager": {"team", "job", "dm", "admin_broadcast"},
    "worker": {"team", "job", "dm"},
    "helper": {"team", "job", "dm"},
    "viewer": {"team", "admin_broadcast"},
    "customer": {"job"},
    "guest": set(),
}


def allowed_channels(role: str) -> Set[str]:
    return set(ROLE_CHANNELS.get((role or "").lower(), set()))


def can_send(role: str, channel_type: str) -> bool:
    return channel_type in allowed_channels(role)


def can_read(role: str, channel_type: str) -> bool:
    return channel_type in allowed_channels(role)
