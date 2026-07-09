# -*- coding: utf-8 -*-
"""Shared mobile page builders — DRY helpers for /mobile/* routes."""
from __future__ import annotations

import html
from typing import Iterable


def mobile_page(title: str, body_html: str, *, nav: str = "home") -> str:
    """Wrap mobile content in standard PWA shell."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{html.escape(title)} — J&amp;R Mobile</title>
<link rel="manifest" href="/static/mobile/manifest.json">
<link rel="stylesheet" href="/static/mobile/mobile.css">
</head>
<body data-nav="{html.escape(nav)}">
<header class="mobile-header"><h1>{html.escape(title)}</h1></header>
<main class="mobile-main">{body_html}</main>
<nav class="mobile-bottom-nav">
  <a href="/mobile" class="{'active' if nav=='home' else ''}">Home</a>
  <a href="/mobile/jobs" class="{'active' if nav=='jobs' else ''}">Jobs</a>
  <a href="/mobile/files" class="{'active' if nav=='files' else ''}">Files</a>
  <a href="/mobile/capture" class="{'active' if nav=='capture' else ''}">Capture</a>
</nav>
<script src="/static/mobile/mobile-outbox.js"></script>
<script src="/static/mobile/mobile-app.js"></script>
</body>
</html>"""


def mobile_card(title: str, lines: Iterable[str]) -> str:
    items = "".join(f"<li>{html.escape(str(x))}</li>" for x in lines)
    return f'<section class="mobile-card"><h2>{html.escape(title)}</h2><ul>{items}</ul></section>'
