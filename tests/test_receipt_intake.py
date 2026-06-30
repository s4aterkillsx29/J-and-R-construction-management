"""Tests for iPhone receipt intake and Garris Evans correction."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class ReceiptIntakeTests(unittest.TestCase):
    def test_gary_evans_corrected_to_garris(self):
        from app.receipt_intake import correct_filename, correct_supplier_text

        self.assertIn("Garris", correct_filename("2026-06-29_Gary_Evans_lumber.jpg"))
        self.assertNotIn("Gary", correct_filename("2026-06-29_Gary_Evans_lumber.jpg"))
        self.assertEqual(correct_supplier_text("Gary Evans"), "Garris Evans")

    def test_lumber_receipt_detected(self):
        from app.receipt_intake import is_lumber_receipt

        self.assertTrue(is_lumber_receipt("2026-06-29_GarrisEvans_2x4.jpg"))
        self.assertTrue(is_lumber_receipt("receipt.pdf", "lumber materials"))
        self.assertFalse(is_lumber_receipt("gas_station.jpg"))

    def test_process_inbox_files_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            inbox = ws / "02_RECEIPTS_PHOTO_INBOX"
            inbox.mkdir(parents=True)
            src = inbox / "2026-06-29_315Lily_Gary_Evans_lumber_89.50.jpg"
            src.write_bytes(b"fake")

            from app.receipt_intake import process_receipt_inbox

            rep = process_receipt_inbox(ws)
            self.assertEqual(rep["processed"], 1)
            self.assertEqual(rep["lumber"], 1)
            filed = list((ws / "06_Bookkeeping_Taxes" / "Receipts_Filed").rglob("*.jpg"))
            self.assertEqual(len(filed), 1)
            self.assertIn("Garris", filed[0].name)
            reg = ws / "08_Admin_Standards" / "LUMBER_PRICE_REGISTER.csv"
            self.assertTrue(reg.is_file())
            self.assertIn("89.50", reg.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
