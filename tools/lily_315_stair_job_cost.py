#!/usr/bin/env python3
"""Internal job-cost sheet for Lily's 315 Sassafras Lane stair rebuilds.

INTERNAL USE ONLY - NOT CUSTOMER COPY
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
INTERNAL_DIR = BASE_DIR / "docs" / "internal" / "lily-315-sassafras"

CUSTOMER_PRICE = 1000.00
STANDARD_PRICE = 1650.00
OWNER_LABOR_RATE = 30.00  # J&R job-costing rate (not a deductible owner wage)
HELPER_DAY_RATE = 140.00
SETS = 2


@dataclass(frozen=True)
class LineItem:
    category: str
    description: str
    qty: float
    unit_cost: float
    notes: str = ""

    @property
    def total(self) -> float:
        return round(self.qty * self.unit_cost, 2)


# Conservative material takeoff for one 4 ft wide, 4-step exterior stair set.
# Uses rounded-up retail pricing so the affordability check errs high.
PER_SET_MATERIALS = [
    LineItem("Materials", "2x12x8 pressure-treated stringer stock", 3, 24.00, "Three pocket-cut stringers"),
    LineItem("Materials", "2x6x8 pressure-treated tread boards", 8, 10.50, "Two treads per step"),
    LineItem("Materials", "1x8x8 pressure-treated kickplate/riser boards", 4, 12.50),
    LineItem("Materials", "2x4x8 pressure-treated handrail stock", 2, 9.00),
    LineItem("Materials", "Structural screws, lags, and anchors", 1, 38.00),
    LineItem("Materials", "Joist hangers / stringer ties / hardware", 1, 32.00),
    LineItem("Materials", "Consumables and 10% waste buffer", 1, 35.00),
]

PER_SET_LABOR = [
    LineItem("Owner Labor", "Layout, pocket stringer cutting, and fitting", 3.5, OWNER_LABOR_RATE),
    LineItem("Owner Labor", "Stringer install, leveling, and attachment", 2.0, OWNER_LABOR_RATE),
    LineItem("Owner Labor", "Double-tread and kickplate install", 2.0, OWNER_LABOR_RATE),
    LineItem("Owner Labor", "Handrail install and final secure", 1.5, OWNER_LABOR_RATE),
    LineItem("Owner Labor", "Cleanup and final walk-through", 1.0, OWNER_LABOR_RATE),
]

PER_SET_OVERHEAD = [
    LineItem("Vehicle / Jobsite", "Truck wear, fuel, and mobilization share", 1, 45.00, "Amortized per set when both sets done same trip"),
    LineItem("Tools / Admin", "Blade wear, bits, phone, scheduling, quote time", 1, 25.00),
]


def money(value: float) -> str:
    return f"${value:,.2f}"


def sum_items(items: list[LineItem]) -> float:
    return round(sum(item.total for item in items), 2)


def analyze_set() -> dict:
    materials = sum_items(PER_SET_MATERIALS)
    owner_labor = sum_items(PER_SET_LABOR)
    overhead = sum_items(PER_SET_OVERHEAD)
    helper_pay = 0.0
    cash_cost = materials + overhead + helper_pay
    cash_margin = round(CUSTOMER_PRICE - cash_cost, 2)
    estimated_profit = round(CUSTOMER_PRICE - cash_cost - owner_labor, 2)
    owner_hours = round(sum(item.qty for item in PER_SET_LABOR), 1)
    effective_hourly = round(estimated_profit / owner_hours, 2) if owner_hours else 0.0
    affordable = cash_margin >= 250 and estimated_profit >= 200
    return {
        "materials": materials,
        "owner_labor": owner_labor,
        "owner_hours": owner_hours,
        "overhead": overhead,
        "helper_pay": helper_pay,
        "cash_cost": cash_cost,
        "cash_margin": cash_margin,
        "estimated_profit": estimated_profit,
        "effective_hourly": effective_hourly,
        "affordable": affordable,
    }


def render_report() -> str:
    one = analyze_set()
    both_materials = round(one["materials"] * SETS, 2)
    both_owner_labor = round(one["owner_labor"] * SETS, 2)
    both_overhead = round(one["overhead"] * SETS - 45.00, 2)  # one shared mobilization
    both_revenue = CUSTOMER_PRICE * SETS
    both_cash_cost = round(both_materials + both_overhead, 2)
    both_cash_margin = round(both_revenue - both_cash_cost, 2)
    both_estimated_profit = round(both_revenue - both_cash_cost - both_owner_labor, 2)
    both_owner_hours = round(one["owner_hours"] * SETS, 1)
    both_effective_hourly = round(both_estimated_profit / both_owner_hours, 2) if both_owner_hours else 0.0
    verdict = "YES - AFFORDABLE" if one["affordable"] and both_estimated_profit >= 500 else "REVIEW NEEDED"

    lines = [
        "INTERNAL USE ONLY - NOT CUSTOMER COPY",
        "J & R Construction - Internal Job Cost Sheet",
        f"Generated: {dt.datetime.now().strftime('%Y-%m-%d %I:%M %p')}",
        "",
        "Customer: Lily",
        "Address: 315 Sassafras Lane",
        "Work: Two separate 4 ft wide exterior stair sets (4 steps each)",
        "Customer price: $1,000.00 per stair set (friends & family rate)",
        "Standard listed price: $1,650.00 per stair set",
        "Helper plan: Solo owner/operator (no helper pay on these sets)",
        "",
        "=== PER SET MATERIAL TAKEOFF (conservative retail) ===",
    ]
    for item in PER_SET_MATERIALS:
        lines.append(f"- {item.description}: {item.qty:g} x {money(item.unit_cost)} = {money(item.total)}")
    lines.extend(
        [
            f"Materials subtotal per set: {money(one['materials'])}",
            "",
            "=== PER SET OWNER LABOR PLAN ===",
        ]
    )
    for item in PER_SET_LABOR:
        lines.append(f"- {item.description}: {item.qty:g} hr x {money(item.unit_cost)}/hr = {money(item.total)}")
    lines.extend(
        [
            f"Owner labor subtotal per set: {money(one['owner_labor'])} ({one['owner_hours']} hours)",
            "",
            "=== PER SET OVERHEAD ===",
        ]
    )
    for item in PER_SET_OVERHEAD:
        lines.append(f"- {item.description}: {money(item.total)}")
    lines.extend(
        [
            f"Overhead subtotal per set: {money(one['overhead'])}",
            "",
            "=== SINGLE SET AFFORDABILITY @ $1,000 ===",
            f"Revenue: {money(CUSTOMER_PRICE)}",
            f"Cash-out costs (materials + overhead, no helper): {money(one['cash_cost'])}",
            f"Cash margin before owner time: {money(one['cash_margin'])}",
            f"Owner labor value (job-costing only): {money(one['owner_labor'])}",
            f"Estimated net after owner time: {money(one['estimated_profit'])}",
            f"Effective owner hourly after all counted costs: {money(one['effective_hourly'])}/hr",
            "",
            "=== BOTH SETS SAME TRIP ===",
            f"Revenue (2 sets): {money(both_revenue)}",
            f"Materials (2 sets): {money(both_materials)}",
            f"Overhead (shared mobilization): {money(both_overhead)}",
            f"Cash margin before owner time: {money(both_cash_margin)}",
            f"Owner labor value (20.0 hrs planned): {money(both_owner_labor)}",
            f"Estimated net after owner time: {money(both_estimated_profit)}",
            f"Effective owner hourly: {money(both_effective_hourly)}/hr",
            "",
            "=== VERDICT ===",
            verdict,
            "",
            "Notes:",
            "- Customer invoices are updated to $1,000.00 per set with $500 deposit / $500 balance.",
            "- This is a friends & family rate, not full market price. Standard price remains $1,650.00 on the invoice.",
            "- Pocket-cut stringers and solo labor keep helper cost at $0.",
            "- Unknown rot, extra landing work, or step-count changes are excluded by the customer invoice clause.",
            "- Large fence work at this property remains a separate future quote.",
            "- Keep receipt photos and actual hours against this sheet when the job is done.",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    INTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    report = render_report()
    out = INTERNAL_DIR / f"INTERNAL_COST_SHEET_LILY_315_STAIRS_{stamp}.txt"
    out.write_text(report, encoding="utf-8")
    print(out)
    print()
    print(report)


if __name__ == "__main__":
    main()
