#!/usr/bin/env python3
"""Generate Lily's chain-link fence customer estimate at 315 Sassafras Lane.

Customer copy only. Gate spec: two (2) four-foot (4 ft) gates.
No eight-foot (8 ft) gate is included in this estimate.
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
import sys
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
IPHONE_DIR = BASE_DIR / "iphone_files" / "Invoices" / "Lily - 315 Sassafras Lane"

BUSINESS_NAME = "J & R Construction"
PHONE = "(910) 712-0936"
OWNER = "Jacob Cosentino"
CUSTOMER = "Lily"
ADDRESS = "315 Sassafras Lane"
JOB_ID = "JRC-JOB-315-LILY-FENCE"
DOC_NO = "EST-JRC-JOB-315-LILY-FENCE-001"
JOB_NAME = "Lily / 315 Sassafras — Chain-Link Fence"
TITLE = "Estimate — Chain-Link Fence (Friends & Family Rate)"

FENCE_LINEAR_FEET = 185
FENCE_HEIGHT_FT = 4
STANDARD_PRICE = 8325.00
CUSTOMER_PRICE = 7200.00
DISCOUNT_AMOUNT = STANDARD_PRICE - CUSTOMER_PRICE
DISCOUNT_LABEL = "Friends & Family Discount"

GATE_COUNT = 2
GATE_WIDTH_FT = 4

FORBIDDEN_GATE_PHRASES = (
    r"8\s*[- ]?ft\s+gate",
    r"8\s*[- ]?foot\s+gate",
    r"eight\s*[- ]?foot\s+gate",
    r"one\s+4\s*[- ]?ft.*one\s+8\s*[- ]?ft",
    r"4\s*[- ]?ft.*8\s*[- ]?ft\s+gate",
)

PAYMENT_TERMS = (
    "50% deposit due before work begins. Remaining 50% balance due upon completion "
    "unless otherwise noted in writing."
)
EXCLUSIONS = (
    "Price may change if hidden damage, rot, rock, roots, drainage issues, utility "
    "conflicts, property-line disputes, code issues, unsafe conditions, or additional "
    "required work is discovered after layout or during installation. Final linear "
    "footage, post spacing, gate locations, and terminal points will be confirmed on "
    "site before work begins. Painting, staining, clearing/grading beyond normal "
    "fence-line cleanup, and optional add-ons are excluded unless specifically "
    "included. This fence estimate is separate from the stair invoices for this property."
)
DISCOUNT_NOTE = (
    "Friends &amp; family best price applied. This reduced rate reflects our "
    "relationship and the combined work planned at 315 Sassafras Lane."
)


def money(value: float) -> str:
    return f"${value:,.2f}"


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %I:%M %p")


def gate_scope() -> str:
    return f"""Gates included in this estimate:
- Gate 1: One (1) four-foot ({GATE_WIDTH_FT} ft) walk gate with standard hinge, latch, and gate hardware.
- Gate 2: One (1) four-foot ({GATE_WIDTH_FT} ft) walk gate with standard hinge, latch, and gate hardware.
- Total gates: Two (2) four-foot ({GATE_WIDTH_FT} ft) gates.
- This estimate does NOT include an eight-foot (8 ft) gate, double-wide gate, or vehicle gate."""


def build_scope() -> str:
    return f"""Install chain-link fence at {ADDRESS} per this estimate.

Fence specification:
- Approximately {FENCE_LINEAR_FEET} linear feet of {FENCE_HEIGHT_FT} ft height galvanized chain-link fence (confirm exact footage on site).
- Line posts, terminal posts, corner/brace posts as required for a standard residential installation.
- Top rail and tension wire as needed for a clean, secure installation.
- Ties, fasteners, concrete for posts, and standard install materials included.
- Layout, post setting, fabric stretch, and final securement.
- Standard walk-gate openings prepared for the two gates listed below.
- Jobsite cleanup of construction debris related to this fence scope.

{gate_scope()}

Customer-facing line items:
- Materials: chain-link fabric, posts, rails, concrete, ties, gate frames, and hardware — $2,850.00
- Labor: layout, post setting, fence run install, and two ({GATE_WIDTH_FT} ft) gate installs — $5,475.00
- Standard fence price — {money(STANDARD_PRICE)}
- {DISCOUNT_LABEL} — -{money(DISCOUNT_AMOUNT)}
- Friends & family price — {money(CUSTOMER_PRICE)}

This estimate covers the fence scope above only. Stair work at this property is billed on separate invoices."""


def verify_customer_copy_text(text: str) -> list[str]:
    errors: list[str] = []
    lower = text.lower()
    for pattern in FORBIDDEN_GATE_PHRASES:
        if re.search(pattern, lower):
            errors.append(f"Forbidden gate wording matched pattern: {pattern}")
    if "total gates: two (2) four-foot (4 ft) gates" not in lower:
        errors.append("Missing required wording: total gates: two (2) four-foot (4 ft) gates")
    if lower.count("four-foot (4 ft) walk gate") < 2:
        errors.append("Expected two separate four-foot (4 ft) walk gate lines")
    if re.search(r"one \(1\) (?:eight|8)[- ]foot", lower):
        errors.append("Customer copy includes a one (1) eight-foot gate")
    if re.search(r"8\s*[- ]?ft\s+walk gate", lower):
        errors.append("Customer copy includes an 8 ft walk gate")
    return errors


def write_estimate() -> tuple[Path, Path, Path, Path]:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{DOC_NO}_{stamp}.pdf"
    export_path = EXPORT_DIR / filename
    docs_path = DOCS_DIR / filename
    send_path = SEND_DIR / "Lily_315_Sassafras_Fence_CUSTOMER_ESTIMATE.pdf"
    iphone_path = IPHONE_DIR / "Lily - Fence Estimate - 7200.pdf"

    for folder in (EXPORT_DIR, DOCS_DIR, SEND_DIR, IPHONE_DIR):
        folder.mkdir(parents=True, exist_ok=True)

    scope = build_scope()
    errors = verify_customer_copy_text(scope)
    if errors:
        raise ValueError("Customer copy gate verification failed:\n- " + "\n- ".join(errors))

    deposit = round(CUSTOMER_PRICE / 2, 2)
    balance = round(CUSTOMER_PRICE - deposit, 2)

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
        Paragraph(f"<b>ESTIMATE</b> &nbsp;&nbsp; {DOC_NO}", normal),
        Paragraph(
            f"<b>Job Document ID:</b> {JOB_ID}<br/>"
            f"<b>Customer:</b> {CUSTOMER}<br/>"
            f"<b>Job:</b> {JOB_NAME}<br/>"
            f"<b>Address:</b> {ADDRESS}",
            normal,
        ),
        Spacer(1, 0.18 * inch),
        Paragraph(f"<b>{TITLE}</b>", normal),
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
                    ["Standard Price", money(STANDARD_PRICE)],
                    [DISCOUNT_LABEL, f"-{money(DISCOUNT_AMOUNT)}"],
                    ["Friends & Family Price", money(CUSTOMER_PRICE)],
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
    shutil.copy2(export_path, send_path)
    shutil.copy2(export_path, iphone_path)
    return export_path, docs_path, send_path, iphone_path


def main() -> int:
    paths = write_estimate()
    for path in paths:
        print(path)
    print("\nGate check: PASSED — customer copy shows two (2) four-foot (4 ft) gates only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
