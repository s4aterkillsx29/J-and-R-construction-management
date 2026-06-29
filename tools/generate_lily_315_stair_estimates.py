#!/usr/bin/env python3
"""Generate two customer invoices for Lily's stair rebuilds at 315 Sassafras Lane."""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BASE_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = BASE_DIR / "exports"
DOCS_DIR = BASE_DIR / "docs" / "quotes" / "lily-315-sassafras"
IPHONE_DIR = BASE_DIR / "iphone_files" / "Invoices" / "Lily - 315 Sassafras Lane"

BUSINESS_NAME = "J & R Construction"
PHONE = "(910) 712-0936"
OWNER = "Jacob Cosentino"
CUSTOMER = "Lily"
ADDRESS = "315 Sassafras Lane"
STANDARD_PRICE = 1650.00
CUSTOMER_PRICE = 1000.00
DISCOUNT_AMOUNT = STANDARD_PRICE - CUSTOMER_PRICE
DISCOUNT_LABEL = "Friends & Family Discount"
PAYMENT_TERMS = (
    "50% deposit due before work begins. Remaining 50% balance due upon completion "
    "unless otherwise noted in writing."
)
EXCLUSIONS = (
    "Price may change if hidden damage, rot, structural issues, code issues, unsafe "
    "conditions, or additional required work is discovered after opening up the work "
    "area. Painting, staining, and optional add-ons are excluded unless specifically "
    "included. This invoice is based on four (4) steps per stair set; any change to step "
    "count or total rise after site verification may adjust the price. "
    "Any large fence project at this property will be quoted separately; this friends "
    "and family stair price is not a combined fence/stair package unless a separate "
    "written estimate is approved."
)
DISCOUNT_NOTE = (
    "Friends &amp; family best price applied. This reduced rate reflects our relationship "
    "and the expected follow-on work at 315 Sassafras Lane, including the possible large "
    "fence project, which will be estimated on its own scope and materials."
)


def money(value: float) -> str:
    return f"${value:,.2f}"


def common_scope() -> str:
    return f"""Rebuild one exterior stair set per this invoice using the following specification:
- Four (4) steps per stair set.
- Each step uses two (2) pressure-treated 2x6 treads — eight (8) tread boards total per stair set.
- Approximately 4 ft clear tread width (confirm exact width on site).
- Four (4) pressure-treated 1x8 kickplates / riser boards.
- Three (3) housed / pocket-cut stringers laid out and cut on site.
- Stair assembly framed, leveled, and secured to existing structure or approved landing points.
- 2x4 handrail installed along the 4-step run per standard safe handhold height.
- Work performed by owner/operator working solo, including stringer layout and cutting.
- Jobsite cleanup of construction debris related to this stair set.

Customer-facing line items:
- Materials: pressure-treated lumber (8 tread boards per set), fasteners, anchors, and related install supplies — $420.00
- Labor: layout, pocket stringer cutting, framing, double-tread and kickplate install, handrail (solo) — $1,230.00
- Standard stair price — {money(STANDARD_PRICE)}
- {DISCOUNT_LABEL} — -{money(DISCOUNT_AMOUNT)}
- Friends & family price — {money(CUSTOMER_PRICE)}"""


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %I:%M %p")


def build_scope(stair_label: str, stair_location: str) -> str:
    return (
        f"{stair_label} — {stair_location}\n\n"
        f"{common_scope()}\n\n"
        f"This invoice covers only the stair set described above. The second stair set at "
        f"{ADDRESS} is billed on a separate invoice."
    )


INVOICES = [
    {
        "job_id": "JRC-JOB-315-LILY-STAIR-SET-01",
        "doc_no": "INV-JRC-JOB-315-LILY-STAIR-SET-01-001",
        "job_name": "Lily / 315 Sassafras — Stair Set 1",
        "title": "Invoice — Stair Set 1 Rebuild (Friends & Family Rate)",
        "stair_label": "Stair Set 1",
        "stair_location": "First stair set at 315 Sassafras Lane (location to be marked on site)",
        "price": CUSTOMER_PRICE,
        "standard_price": STANDARD_PRICE,
        "discount": DISCOUNT_AMOUNT,
    },
    {
        "job_id": "JRC-JOB-315-LILY-STAIR-SET-02",
        "doc_no": "INV-JRC-JOB-315-LILY-STAIR-SET-02-001",
        "job_name": "Lily / 315 Sassafras — Stair Set 2",
        "title": "Invoice — Stair Set 2 Rebuild (Friends & Family Rate)",
        "stair_label": "Stair Set 2",
        "stair_location": "Second stair set at 315 Sassafras Lane (location to be marked on site)",
        "price": CUSTOMER_PRICE,
        "standard_price": STANDARD_PRICE,
        "discount": DISCOUNT_AMOUNT,
    },
]


def write_invoice(invoice: dict) -> tuple[Path, Path]:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{invoice['doc_no']}_{stamp}.pdf"
    export_path = EXPORT_DIR / filename
    docs_path = DOCS_DIR / filename
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    deposit = round(invoice["price"] / 2, 2)
    balance = round(invoice["price"] - deposit, 2)
    scope = build_scope(invoice["stair_label"], invoice["stair_location"])

    styles = getSampleStyleSheet()
    normal = ParagraphStyle("jrc_normal", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=13)
    small = ParagraphStyle("jrc_small", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#475569"))
    header = ParagraphStyle("jrc_header", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=17, textColor=colors.HexColor("#111827"))

    doc = SimpleDocTemplate(
        str(export_path),
        pagesize=letter,
        rightMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
    )
    story = [
        Paragraph(BUSINESS_NAME, header),
        Paragraph(f"Phone: {PHONE} | Created: {now_stamp()}", normal),
        Paragraph(f"Owned and operated by {OWNER}", small),
        Spacer(1, 0.18 * inch),
        Paragraph(f"<b>INVOICE</b> &nbsp;&nbsp; {invoice['doc_no']}", normal),
        Paragraph(
            f"<b>Job Document ID:</b> {invoice['job_id']}<br/>"
            f"<b>Customer:</b> {CUSTOMER}<br/>"
            f"<b>Job:</b> {invoice['job_name']}<br/>"
            f"<b>Address:</b> {ADDRESS}",
            normal,
        ),
        Spacer(1, 0.18 * inch),
        Paragraph(f"<b>{invoice['title']}</b>", normal),
        Spacer(1, 0.08 * inch),
        Paragraph("<b>Scope of Work</b>", normal),
    ]
    for para in scope.split("\n"):
        if para.strip():
            story.append(Paragraph(para.strip(), normal))

    story.extend(
        [
            Spacer(1, 0.18 * inch),
            Table(
                [
                    ["Standard Price", money(invoice["standard_price"])],
                    [DISCOUNT_LABEL, f"-{money(invoice['discount'])}"],
                    ["Friends & Family Price", money(invoice["price"])],
                    ["Deposit Due Before Work Begins", money(deposit)],
                    ["Balance Due Upon Completion", money(balance)],
                ],
                colWidths=[3.25 * inch, 2 * inch],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dcfce7")),
                        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#ecfdf5")),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                        ("PADDING", (0, 0), (-1, -1), 8),
                    ]
                ),
            ),
            Spacer(1, 0.18 * inch),
            Paragraph(f"<b>Discount Note</b><br/>{DISCOUNT_NOTE}", normal),
            Spacer(1, 0.12 * inch),
            Paragraph(f"<b>Payment Terms</b><br/>{PAYMENT_TERMS}", normal),
            Spacer(1, 0.08 * inch),
            Paragraph(f"<b>Notes / Exclusions</b><br/>{EXCLUSIONS}", normal),
            Spacer(1, 0.12 * inch),
            Paragraph(
                "<i>Customer-facing copy. Internal cost sheets, helper payment notes, and tax/profit notes are excluded by J&amp;R standard.</i>",
                small,
            ),
        ]
    )
    doc.build(story)
    docs_path.write_bytes(export_path.read_bytes())
    iphone_path = save_to_iphone_files(export_path, invoice)
    return export_path, docs_path, iphone_path


def save_to_iphone_files(source_pdf: Path, invoice: dict) -> Path:
    """Copy invoice PDF to the iPhone Files-friendly exports folder."""
    IPHONE_DIR.mkdir(parents=True, exist_ok=True)
    stair_no = "1" if "SET-01" in invoice["job_id"] else "2"
    friendly_name = f"Lily - Stair Set {stair_no} Invoice - 1000.pdf"
    dest = IPHONE_DIR / friendly_name
    shutil.copy2(source_pdf, dest)
    readme = IPHONE_DIR.parents[1] / "OPEN_ON_IPHONE.txt"
    if not readme.exists():
        readme.write_text(
            "J & R Construction - iPhone Files\n"
            "================================\n\n"
            "Find invoices on your iPhone:\n"
            "1. Open the Files app.\n"
            "2. Tap Browse.\n"
            "3. If you use Dropbox with J&R: Dropbox > your J&R folder > iphone_files > Invoices.\n"
            "4. If you use iCloud Drive: iCloud Drive > J&R Construction > iphone_files > Invoices.\n"
            "5. If you use the J&R mobile host: open Mobile > Files on your phone browser.\n\n"
            "Lily stair invoices folder:\n"
            "iphone_files / Invoices / Lily - 315 Sassafras Lane\n",
            encoding="utf-8",
        )
    return dest


def main() -> None:
    for invoice in INVOICES:
        export_path, docs_path, iphone_path = write_invoice(invoice)
        print(export_path)
        print(docs_path)
        print(iphone_path)


if __name__ == "__main__":
    main()
