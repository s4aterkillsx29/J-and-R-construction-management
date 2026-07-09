# -*- coding: utf-8 -*-
"""Calculate job costing preview using J&R standard rates."""
from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "calculate_job_costing",
        "description": "Estimate internal job cost from owner days, helper days, materials, dump fee.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner_days": {"type": "number", "default": 1},
                "helper_days": {"type": "number", "default": 0},
                "materials": {"type": "number", "default": 0},
                "dump_fee": {"type": "number", "default": 0},
            },
            "required": [],
        },
    },
}


def run(
    *,
    owner_days: float = 1,
    helper_days: float = 0,
    materials: float = 0,
    dump_fee: float = 0,
    **kwargs,
) -> dict:
    owner_rate = 240.0
    helper_rate = 140.0
    dump_trip = 50.0
    owner_cost = float(owner_days) * owner_rate
    helper_cost = float(helper_days) * helper_rate
    helper_overhead = 50.0 * max(0, int(helper_days)) if helper_days else 0
    dump_total = float(dump_fee) + (dump_trip if dump_fee else 0)
    materials_cost = float(materials)
    total = owner_cost + helper_cost + helper_overhead + dump_total + materials_cost
    lines = [
        "=== Internal Job Costing Preview ===",
        f"Owner: {owner_days} day(s) × ${owner_rate:.0f}/day = ${owner_cost:.2f}",
        f"Helper: {helper_days} day(s) × ${helper_rate:.0f}/day = ${helper_cost:.2f}",
        f"Helper overhead: ${helper_overhead:.2f}",
        f"Materials: ${materials_cost:.2f}",
        f"Dump: ${dump_fee:.2f} + ${dump_trip:.0f} trip = ${dump_total:.2f}",
        f"Estimated internal total: ${total:.2f}",
        "",
        "Customer pricing and margin stay in internal workup — not on customer PDF unless quoted.",
    ]
    text = "\n".join(lines)
    return {"ok": True, "total_internal": total, "preview_text": text}
