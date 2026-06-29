#!/usr/bin/env python3
"""Copy Lily customer invoices to OneDrive and print share-link steps."""

from __future__ import annotations

import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
CUSTOMER_SEND = BASE_DIR / "customer_send" / "lily-315-sassafras"
ONEDRIVE_MIRROR = BASE_DIR / "onedrive_files" / "Customer_Send" / "Lily - 315 Sassafras Lane"
LINK_FILE = CUSTOMER_SEND / "CUSTOMER_LINK.txt"

STAIR_SET_1 = "Lily_315_Sassafras_Stair_Set_1_CUSTOMER_INVOICE.pdf"
ONEDRIVE_REL = Path("Desktop") / "J and R Construction" / "02_Documents_Invoices_Estimates_Quotes" / "Lily_315_Sassafras"


def onedrive_roots() -> list[Path]:
    home = Path.home()
    roots = [
        home / "OneDrive",
        home / "OneDrive - Personal",
        home / "OneDrive - J and R Construction",
    ]
    return [root for root in roots if root.is_dir()]


def main() -> int:
    source = CUSTOMER_SEND / STAIR_SET_1
    if not source.is_file():
        print(f"Missing customer PDF: {source}")
        return 1

    ONEDRIVE_MIRROR.mkdir(parents=True, exist_ok=True)
    mirror_path = ONEDRIVE_MIRROR / "Lily - Stair Set 1 Invoice - 1000.pdf"
    shutil.copy2(source, mirror_path)
    print(f"Repo mirror ready: {mirror_path}")

    copied = False
    for root in onedrive_roots():
        target_dir = root / ONEDRIVE_REL
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / STAIR_SET_1
        shutil.copy2(source, target)
        print(f"Copied to OneDrive: {target}")
        copied = True

    print()
    print("CREATE THE CUSTOMER ONEDRIVE LINK (30 seconds):")
    print("1. Open File Explorer or onedrive.com")
    print(f"2. Go to: {ONEDRIVE_REL}")
    print(f"3. Right-click: {STAIR_SET_1}")
    print("4. Share -> Anyone with the link can view -> Copy link")
    print("5. Paste that link into customer_send/lily-315-sassafras/CUSTOMER_LINK.txt")
    print()
    print("Send Lily that OneDrive link, or use your JRC host:")
    print("  /customer/lily-315/stair-set-1/download")
    return 0 if copied or mirror_path.is_file() else 2


if __name__ == "__main__":
    raise SystemExit(main())
