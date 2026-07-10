# -*- coding: utf-8 -*-
"""Branded share link + auth gate."""
from __future__ import annotations

import unittest

from app.auth_gate import is_public_path


class BrandedShareLinkTests(unittest.TestCase):
    def test_primary_share_link_public(self) -> None:
        self.assertTrue(is_public_path("/goJandRconstruction"))
        self.assertTrue(is_public_path("/goJandRConstruction"))

    def test_legacy_go_public(self) -> None:
        self.assertTrue(is_public_path("/go"))

    def test_jrc_short_link_public(self) -> None:
        self.assertTrue(is_public_path("/jrc"))
        self.assertTrue(is_public_path("/JRC"))

    def test_jand_r_construction_still_public(self) -> None:
        self.assertTrue(is_public_path("/JandRConstruction"))
        self.assertTrue(is_public_path("/jandRconstruction"))

    def test_connect_still_public(self) -> None:
        self.assertTrue(is_public_path("/connect"))


if __name__ == "__main__":
    unittest.main()
