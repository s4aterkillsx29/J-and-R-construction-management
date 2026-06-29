#!/usr/bin/env python3
"""Reorganize J&R Dropbox business root to standard folders without losing files."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.jrc_dropbox_organization import main

if __name__ == "__main__":
    raise SystemExit(main())
