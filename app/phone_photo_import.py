# -*- coding: utf-8 -*-
"""Stage phone photos / receipt captures for Dropbox business inbox + desktop Cursor analysis."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parents[1]
INBOX_SUBDIR = "00_START_HERE/PHONE_INBOX"

# Receipt records extracted from phone Cursor chat photos (2026-07-01 session).
SESSION_RECEIPTS: List[Dict[str, Any]] = [
    {
        "id": "01_lowes_shelf_brackets",
        "type": "receipt",
        "vendor": "Lowe's",
        "store_number": "0537",
        "location": "N. Myrtle Beach, SC",
        "phone": "(843) 272-1238",
        "date": "2023-08-21",
        "time": "12:47 PM",
        "subtotal": 12.90,
        "tax": 1.03,
        "total": 13.93,
        "payment": "Credit card ending 8000",
        "cashier": "KIMBERLY",
        "category": "Materials & Supplies",
        "items": [
            {"sku": "47683", "desc": "30-IN WHT PLSTC SHLF BRKT", "price": 2.98},
            {"sku": "47682", "desc": "12-IN WHT PLSTC SHLF BRKT", "price": 2.48, "qty": 4},
        ],
        "notes": "Shelf bracket hardware — assign to job materials expense when matched.",
    },
    {
        "id": "02_homedepot_smithfield",
        "type": "receipt",
        "vendor": "The Home Depot",
        "store_number": "3648",
        "location": "1220 E Charlotte Highway, Smithfield, NC 27577",
        "phone": "(919) 934-0100",
        "manager": "MIKE ALLEN",
        "date": "2024-06-12",
        "time": "11:32 AM",
        "cashier": "RICHARD",
        "subtotal": 17.48,
        "tax": 1.27,
        "total": 18.75,
        "payment": "Cash $20.00, change $1.25",
        "category": "Materials & Supplies",
        "items": [
            {"sku": "042820120152", "desc": "HD STAINLESS SW (LOCAL MAINT DEPT 25)", "price": 13.98},
            {"sku": "000000000000", "desc": "BULK CARPENTER PENCILS HD", "qty": 10, "unit": 0.35, "price": 3.50},
        ],
        "pro_home_spent_ytd": 724.16,
        "return_policy_expires": "2024-09-10",
        "notes": "Stainless switch + bulk pencils.",
    },
    {
        "id": "03_homedepot_salinas_cpvc",
        "type": "receipt",
        "vendor": "The Home Depot",
        "store_number": "0617",
        "location": "1215 North Main St, Salinas, CA 93906",
        "phone": "(831) 444-9100",
        "date": "2022-05-31",
        "time": "11:28 AM",
        "cashier": "MARIA",
        "subtotal": 8.27,
        "tax": 0.70,
        "total": 8.97,
        "payment": "Cash $10.00, change $1.03",
        "category": "Materials & Supplies — Plumbing",
        "items": [
            {"sku": "031669000000", "desc": "1/2 IN CPVC CAP", "price": 1.18, "qty": 6},
            {"sku": "031669000000", "desc": "1/2 IN CPVC CAP (2 @ $1.18)", "price": 2.37},
        ],
        "return_policy_expires": "2022-08-29",
        "notes": "CPVC cap fittings.",
    },
    {
        "id": "04_handwritten_jackie_payment",
        "type": "payment_note",
        "vendor": None,
        "date": None,
        "category": "Income / Customer Payment",
        "customer": "Jackie",
        "reference": "403",
        "lines": [
            {"label": "Wayns", "amount": 300, "note": "June 30"},
            {"label": "paid", "amount": 950},
            {"label": "Jackie paid (total)", "amount": 1250},
        ],
        "notes": "Handwritten note: $300 (Wayns, June 30) + $950 paid = $1,250 total from Jackie. Ref 403.",
    },
    {
        "id": "05_truist_deposit",
        "type": "bank_deposit",
        "vendor": "Truist",
        "date": "2024-05-16",
        "time": "14:31:44",
        "category": "Bank Deposit",
        "amount": 1232.31,
        "transaction_type": "Commercial Deposit",
        "check_number": "1052",
        "sequence": "00000196",
        "atm": "NC-CLT-002-ATM-1",
        "reference": "05/16/2024 113 000002 0001",
        "notes": "Commercial deposit receipt — match to customer payment or job income.",
    },
]


def _format_record(rec: Dict[str, Any]) -> str:
    lines = [
        f"J & R Construction — Phone Import Record",
        f"Record ID: {rec.get('id')}",
        f"Type: {rec.get('type')}",
        f"Imported: {datetime.now().isoformat(timespec='seconds')}",
        "",
    ]
    for key, val in rec.items():
        if key in ("id", "type", "items", "lines"):
            continue
        if val is not None:
            lines.append(f"{key.replace('_', ' ').title()}: {val}")
    if rec.get("items"):
        lines.extend(["", "Line items:"])
        for item in rec["items"]:
            lines.append(f"  - {item}")
    if rec.get("lines"):
        lines.extend(["", "Payment lines:"])
        for line in rec["lines"]:
            lines.append(f"  - {line}")
    lines.extend(
        [
            "",
            "Photo status: ORIGINAL IMAGE NOT ATTACHED — save camera photo to this folder",
            f"  as {rec.get('id')}.jpg (or .png) on phone, then re-run push.",
            "",
            "Desktop Cursor prompt:",
            f'  "Analyze 00_START_HERE/PHONE_INBOX/{rec.get("id")}.txt and match to jobs/expenses."',
        ]
    )
    return "\n".join(lines)


def stage_session(
    session_id: Optional[str] = None,
    *,
    business_root: Optional[Path] = None,
    records: Optional[List[Dict[str, Any]]] = None,
) -> Path:
    """Write receipt records + manifest into local business inbox folder."""
    from app.dropbox_workspace import CLOUD_MIRROR_DIR, resolve_business_root

    stamp = session_id or datetime.now().strftime("%Y-%m-%d_cursor-upload")
    root = business_root or resolve_business_root() or CLOUD_MIRROR_DIR
    inbox = root / INBOX_SUBDIR / stamp
    inbox.mkdir(parents=True, exist_ok=True)

    payload = records if records is not None else SESSION_RECEIPTS
    for rec in payload:
        (inbox / f"{rec['id']}.txt").write_text(_format_record(rec), encoding="utf-8")

    manifest = {
        "session_id": stamp,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": "phone_cursor_chat_photos",
        "record_count": len(payload),
        "records": [{"id": r["id"], "type": r.get("type"), "vendor": r.get("vendor"), "total": r.get("total") or r.get("amount")} for r in payload],
        "dropbox_target": f"{INBOX_SUBDIR}/{stamp}",
        "next_steps": [
            "Save original receipt photos from phone camera roll into this folder.",
            "Run: python -m app.phone_photo_import --push",
            "On desktop Cursor: open Dropbox business folder and say 'analyze PHONE_INBOX'",
        ],
    }
    (inbox / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (inbox / "README.txt").write_text(
        "\n".join(
            [
                "PHONE INBOX — Cursor photo upload staging",
                "",
                f"Session: {stamp}",
                "",
                "This folder was created from photos sent in phone Cursor chat.",
                "Structured receipt data is in the .txt files. Original image files",
                "must be saved here from your phone camera roll for full OCR backup.",
                "",
                "Push to Dropbox (cloud agent or office PC with token):",
                "  python -m app.phone_photo_import --push",
                "",
                "Desktop analysis:",
                '  Open Dropbox business folder in Cursor and ask:',
                f'  "Read 00_START_HERE/PHONE_INBOX/{stamp}/MANIFEST.json and log expenses."',
            ]
        ),
        encoding="utf-8",
    )
    (root / ".jrc_dropbox_mirror").write_text("staged\n", encoding="utf-8")
    return inbox


def push_to_dropbox(inbox_dir: Path) -> List[Dict[str, Any]]:
    """Upload staged inbox folder to Dropbox via API."""
    from app.dropbox_workspace import api_upload_folder, get_dropbox_access_token

    if not get_dropbox_access_token():
        raise RuntimeError(
            "DROPBOX_ACCESS_TOKEN not set. Add token to Cursor Cloud Agent secrets "
            "(files.content.write scope) or run on office PC with Dropbox synced."
        )
    rel = f"{INBOX_SUBDIR}/{inbox_dir.name}"
    return api_upload_folder(inbox_dir, rel)


def copy_to_chatgpt_imports(inbox_dir: Path) -> Path:
    """Mirror inbox into local chatgpt_imports for Construction Manager file scan."""
    dest = Path(
        __import__("os").environ.get("JRC_CHATGPT_IMPORTS_DIR", str(BASE_DIR / "chatgpt_imports"))
    ).expanduser()
    target = dest / "phone_inbox" / inbox_dir.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(inbox_dir, target)
    return target


def main(argv: Optional[List[str]] = None) -> int:
    import sys

    args = list(argv if argv is not None else sys.argv[1:])
    if not args or args[0] in ("--stage", "stage"):
        inbox = stage_session()
        print(f"Staged {len(SESSION_RECEIPTS)} records -> {inbox}")
        return 0

    if args[0] in ("--push", "push"):
        from app.dropbox_workspace import CLOUD_MIRROR_DIR, resolve_business_root

        root = resolve_business_root() or CLOUD_MIRROR_DIR
        inbox_root = root / INBOX_SUBDIR
        if not inbox_root.is_dir():
            print("No PHONE_INBOX found. Run: python -m app.phone_photo_import --stage")
            return 1
        sessions = sorted([p for p in inbox_root.iterdir() if p.is_dir()], reverse=True)
        if not sessions:
            print("No inbox sessions found.")
            return 1
        inbox = sessions[0]
        try:
            results = push_to_dropbox(inbox)
            print(f"Pushed {len(results)} file(s) from {inbox.name} to Dropbox.")
            for row in results:
                print(f"  {row['dropbox']}")
            return 0
        except Exception as exc:
            print(f"Push failed: {exc}")
            return 1

    if args[0] in ("--mirror-local", "mirror-local"):
        from app.dropbox_workspace import CLOUD_MIRROR_DIR

        inbox_root = CLOUD_MIRROR_DIR / INBOX_SUBDIR
        sessions = sorted([p for p in inbox_root.iterdir() if p.is_dir()], reverse=True) if inbox_root.is_dir() else []
        if not sessions:
            inbox = stage_session()
        else:
            inbox = sessions[0]
        target = copy_to_chatgpt_imports(inbox)
        print(f"Mirrored to {target}")
        return 0

    print("Usage: python -m app.phone_photo_import [--stage | --push | --mirror-local]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
