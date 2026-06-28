#!/usr/bin/env python3
"""Generate two customer estimates for Lily's stair rebuilds at 315 Sassafras Lane."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BASE_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = BASE_DIR / "exports"

BUSINESS_NAME = "J & R Construction"
PHONE = "(910) 712-0936"
OWNER = "Jacob Cosentino"
CUSTOMER = "Lily"
ADDRESS = "315 Sassafras Lane"
PAYMENT_TERMS = (
    "50% deposit due before work begins. Remaining 50% balance due upon completion "
    "unless otherwise noted in writing."
)
EXCLUSIONS = (
    "Price may change if hidden damage, rot, structural issues, code issues, unsafe "
    "conditions, or additional required work is discovered after opening up the work "
    "area. Painting, staining, and optional add-ons are excluded unless specifically "
    "included. This quote is based on four (4) steps per stair set; any change to step "
    "count or total rise after site verification may adjust the price."
)

COMMON_SCOPE = """Rebuild one exterior stair set per this quote using the following specification:
- Four (4) steps per stair set.
- Approximately 4 ft clear tread width (confirm exact width on site).
- Four (4) pressure-treated 2x6 treads.
- Four (4) pressure-treated 1x8 kickplates / riser boards.
- Three (3) housed / pocket-cut stringers laid out and cut on site.
- Stair assembly framed, leveled, and secured to existing structure or approved landing points.
- 2x4 handrail installed along the 4-step run per standard safe handhold height.
- Work performed by owner/operator working solo, including stringer layout and cutting.
- Jobsite cleanup of construction debris related to this stair set.

Customer-facing line items:
- Materials: pressure-treated lumber, fasteners, anchors, and related install supplies — $400.00
- Labor: layout, pocket stringer cutting, framing, tread/kickplate install, handrail (solo) — $1,250.00"""


def money(value: float) -> str:
    return f"${value:,.2f}"


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %I:%M %p")


def build_scope(stair_label: str, stair_location: str) -> str:
    return (
        f"{stair_label} — {stair_location}\n\n"
        f"{COMMON_SCOPE}\n\n"
        f"This quote covers only the stair set described above. The second stair set at "
        f"{ADDRESS} is quoted separately."
    )


QUOTES = [
    {
        "job_id": "JRC-JOB-315-LILY-STAIR-SET-01",
        "doc_no": "EST-JRC-JOB-315-LILY-STAIR-SET-01-001",
        "job_name": "Lily / 315 Sassafras — Stair Set 1",
        "title": "Estimate — Stair Set 1 Rebuild",
        "stair_label": "Stair Set 1",
        "stair_location": "First stair set at 315 Sassafras Lane (location to be marked on site)",
        "price": 1650.00,
    },
    {
        "job_id": "JRC-JOB-315-LILY-STAIR-SET-02",
        "doc_no": "EST-JRC-JOB-315-LILY-STAIR-SET-02-001",
        "job_name": "Lily / 315 Sassafras — Stair Set 2",
        "title": "Estimate — Stair Set 2 Rebuild",
        "stair_label": "Stair Set 2",
        "stair_location": "Second stair set at 315 Sassafras Lane (location to be marked on site)",
        "price": 1650.00,
    },
]


def write_estimate(quote: dict) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / f"{quote['doc_no']}_{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
    deposit = round(quote["price"] / 2, 2)
    balance = round(quote["price"] - deposit, 2)
    scope = build_scope(quote["stair_label"], quote["stair_location"])

    styles = getSampleStyleSheet()
    normal = ParagraphStyle("jrc_normal", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=13)
    small = ParagraphStyle("jrc_small", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#475569"))
    header = ParagraphStyle("jrc_header", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=17, textColor=colors.HexColor("#111827"))

    doc = SimpleDocTemplate(
        str(path),
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
        Paragraph(f"<b>ESTIMATE</b> &nbsp;&nbsp; {quote['doc_no']}", normal),
        Paragraph(
            f"<b>Job Document ID:</b> {quote['job_id']}<br/>"
            f"<b>Customer:</b> {CUSTOMER}<br/>"
            f"<b>Job:</b> {quote['job_name']}<br/>"
            f"<b>Address:</b> {ADDRESS}",
            normal,
        ),
        Spacer(1, 0.18 * inch),
        Paragraph(f"<b>{quote['title']}</b>", normal),
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
                    ["Total Customer Price", money(quote["price"])],
                    ["Deposit Due Before Work Begins", money(deposit)],
                    ["Balance Due Upon Completion", money(balance)],
                ],
                colWidths=[3.25 * inch, 2 * inch],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dcfce7")),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                        ("PADDING", (0, 0), (-1, -1), 8),
                    ]
                ),
            ),
            Spacer(1, 0.18 * inch),
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
    return path


def main() -> None:
    paths = [write_estimate(q) for q in QUOTES]
    for p in paths:
        print(p)


if __name__ == "__main__":
    main()
