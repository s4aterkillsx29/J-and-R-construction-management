# -*- coding: utf-8 -*-
"""Role → channel permissions for messenger."""
from __future__ import annotations

from typing import Set

ROLE_CHANNELS: dict[str, Set[str]] = {
    "admin": {"team", "job", "dm", "admin_broadcast", "announcement"},
    "manager": {"team", "job", "dm", "admin_broadcast"},
    "worker": {"team", "job", "dm", "admin_broadcast"},
    "helper": {"team", "job", "dm", "admin_broadcast"},
    "viewer": {"team", "admin_broadcast"},
    "customer": {"job", "admin_broadcast"},
    "guest": set(),
}

# Channels where non-admin roles may read but not post
BROADCAST_CHANNELS = frozenset({"admin_broadcast", "announcement"})


def allowed_channels(role: str) -> Set[str]:
    return set(ROLE_CHANNELS.get((role or "").lower(), set()))


def can_send(role: str, channel_type: str) -> bool:
    role = (role or "").lower()
    if role == "viewer":
        return False
    ch = channel_type or ""
    if ch in BROADCAST_CHANNELS:
        return role == "admin"
    return ch in allowed_channels(role)


def can_read(role: str, channel_type: str) -> bool:
    ch = channel_type or ""
    if ch in allowed_channels(role):
        return True
    # Office announcements visible to all signed-in roles with dashboard access
    if ch in BROADCAST_CHANNELS:
        return role in ROLE_CHANNELS and role != "guest"
    return False
