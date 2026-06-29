#!/usr/bin/env python3
"""Generate two customer invoices for Lily's 4 ft stair rebuilds at 315 Sassafras Lane.

Send-ready copies use a clean $1,000.00 total per stair set with no confusing
higher reference prices on the customer-facing document.
"""

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
SEND_DIR = DOCS_DIR / "SEND_TO_LILY"
ARCHIVE_DIR = DOCS_DIR / "_archive"
IPHONE_DIR = BASE_DIR / "iphone_files" / "Invoices" / "Lily - 315 Sassafras Lane"

BUSINESS_NAME = "J & R Construction"
PHONE = "(910) 712-0936"
OWNER = "Jacob Cosentino"
CUSTOMER = "Lily"
ADDRESS = "315 Sassafras Lane"
INVOICE_TOTAL = 1000.00
MATERIALS_LINE = 320.00
LABOR_LINE = 680.00

PAYMENT_TERMS = (
    "50% deposit due before work begins. Remaining 50% balance due upon completion "
    "unless otherwise noted in writing."
)
EXCLUSIONS = (
    "Price may change if hidden damage, rot, structural issues, code issues, unsafe "
    "conditions, or additional required work is discovered after opening up the work "
    "area. Painting, staining, and optional add-ons are excluded unless specifically "
    "included. This invoice is based on four (4) steps per stair set with approximately "
    "4 ft tread width; any change to step count, width, or total rise after site "
    "verification may adjust the price. Any fence work at this property is quoted "
    "separately on its own estimate."
)
INVOICE_NOTE = (
    "Friends &amp; family invoice rate for one 4 ft wide exterior stair set at "
    f"{ADDRESS}. This invoice covers only the stair set listed above."
)


def money(value: float) -> str:
    return f"${value:,.2f}"


def common_scope() -> str:
    return """Rebuild one exterior stair set per this invoice using the following specification:
- Four (4) steps per stair set.
- Approximately 4 ft clear tread width (confirm exact width on site).
- Each step uses two (2) pressure-treated 2x6 treads — eight (8) tread boards total per stair set.
- Four (4) pressure-treated 1x8 kickplates / riser boards.
- Three (3) housed / pocket-cut stringers laid out and cut on site.
- Stair assembly framed, leveled, and secured to existing structure or approved landing points.
- 2x4 handrail installed along the 4-step run per standard safe handhold height.
- Work performed by owner/operator working solo, including stringer layout and cutting.
- Jobsite cleanup of construction debris related to this stair set."""


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
        "send_name": "Lily_315_Sassafras_Stair_Set_1_CUSTOMER_INVOICE.pdf",
        "iphone_name": "Lily - Stair Set 1 Invoice - 1000.pdf",
        "job_name": "Lily / 315 Sassafras — Stair Set 1 (4 ft)",
        "title": "Invoice — 4 ft Stair Set 1 Rebuild",
        "stair_label": "Stair Set 1",
        "stair_location": "First 4 ft stair set at 315 Sassafras Lane (location to be marked on site)",
        "price": INVOICE_TOTAL,
    },
    {
        "job_id": "JRC-JOB-315-LILY-STAIR-SET-02",
        "doc_no": "INV-JRC-JOB-315-LILY-STAIR-SET-02-001",
        "send_name": "Lily_315_Sassafras_Stair_Set_2_CUSTOMER_INVOICE.pdf",
        "iphone_name": "Lily - Stair Set 2 Invoice - 1000.pdf",
        "job_name": "Lily / 315 Sassafras — Stair Set 2 (4 ft)",
        "title": "Invoice — 4 ft Stair Set 2 Rebuild",
        "stair_label": "Stair Set 2",
        "stair_location": "Second 4 ft stair set at 315 Sassafras Lane (location to be marked on site)",
        "price": INVOICE_TOTAL,
    },
]


def write_invoice(invoice: dict) -> tuple[Path, Path, Path, Path]:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_name = f"{invoice['doc_no']}_{stamp}.pdf"
    export_path = EXPORT_DIR / archive_name
    archive_path = ARCHIVE_DIR / archive_name

    for folder in (EXPORT_DIR, DOCS_DIR, SEND_DIR, ARCHIVE_DIR, IPHONE_DIR):
        folder.mkdir(parents=True, exist_ok=True)

    send_path = SEND_DIR / invoice["send_name"]
    iphone_path = IPHONE_DIR / invoice["iphone_name"]

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
            Paragraph("<b>Invoice Amount</b>", normal),
            Spacer(1, 0.06 * inch),
            Table(
                [
                    ["Materials & supplies", money(MATERIALS_LINE)],
                    ["Labor (solo owner/operator)", money(LABOR_LINE)],
                    ["Invoice Total", money(invoice["price"])],
                    ["Deposit Due Before Work Begins", money(deposit)],
                    ["Balance Due Upon Completion", money(balance)],
                ],
                colWidths=[3.25 * inch, 2 * inch],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#ecfdf5")),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                        ("PADDING", (0, 0), (-1, -1), 8),
                    ]
                ),
            ),
            Spacer(1, 0.18 * inch),
            Paragraph(f"<b>Invoice Note</b><br/>{INVOICE_NOTE}", normal),
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

    pdf_bytes = export_path.read_bytes()
    archive_path.write_bytes(pdf_bytes)
    send_path.write_bytes(pdf_bytes)
    iphone_path.write_bytes(pdf_bytes)
    return export_path, archive_path, send_path, iphone_path


def cleanup_old_copies() -> list[str]:
    """Move old timestamped stair invoice PDFs out of the main quotes folder."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    removed: list[str] = []
    for path in DOCS_DIR.glob("INV-JRC-JOB-315-LILY-STAIR-SET-*.pdf"):
        dest = ARCHIVE_DIR / path.name
        shutil.move(str(path), str(dest))
        removed.append(f"{path.name} -> _archive/")
    return removed


def write_send_readme() -> Path:
    readme = SEND_DIR / "README_SEND_TO_LILY.txt"
    readme.write_text(
        "Lily — 315 Sassafras Lane — SEND THESE FILES\n"
        "============================================\n\n"
        "Stair invoices (4 ft sets) — $1,000.00 each:\n"
        "- Lily_315_Sassafras_Stair_Set_1_CUSTOMER_INVOICE.pdf\n"
        "- Lily_315_Sassafras_Stair_Set_2_CUSTOMER_INVOICE.pdf\n\n"
        "Each invoice total: $1,000.00\n"
        "Deposit before work: $500.00\n"
        "Balance on completion: $500.00\n\n"
        "Fence estimate (separate):\n"
        "- Lily_315_Sassafras_Fence_CUSTOMER_ESTIMATE.pdf\n\n"
        "Regenerate stair invoices:\n"
        "  python tools/generate_lily_315_stair_estimates.py\n",
        encoding="utf-8",
    )
    return readme


def main() -> None:
    archived = cleanup_old_copies()
    for invoice in INVOICES:
        export_path, archive_path, send_path, iphone_path = write_invoice(invoice)
        print("SEND TO LILY:", send_path)
        print("iPhone copy:", iphone_path)
        print("Archive:", archive_path)
        print("Export:", export_path)
        print()
    write_send_readme()
    if archived:
        print("Archived old duplicate copies:")
        for line in archived:
            print(" ", line)


if __name__ == "__main__":
    main()
