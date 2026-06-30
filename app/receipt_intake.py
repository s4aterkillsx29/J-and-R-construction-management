# -*- coding: utf-8 -*-
"""iPhone receipt photo inbox — file, correct names, lumber price register."""
from __future__ import annotations

import csv
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

INBOX_DIR = "02_RECEIPTS_PHOTO_INBOX"
FILED_DIR = "06_Bookkeeping_Taxes/Receipts_Filed"
REGISTER_REL = "08_Admin_Standards/LUMBER_PRICE_REGISTER.csv"
LUMBER_RULES_REL = "08_Admin_Standards/LOG_SYNC_RULES_LUMBER_RECEIPTS.txt"
MANIFEST_NAME = ".receipt_intake_manifest.json"

RECEIPT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".pdf", ".gif"}

# Supplier corrections — lumber supplier is Garris Evans, NOT Gary Evans.
SUPPLIER_CORRECTIONS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"gary\s*evans?", re.I), "Garris_Evans"),
    (re.compile(r"gary_evans?", re.I), "Garris_Evans"),
    (re.compile(r"gary-evans?", re.I), "Garris-Evans"),
]

LUMBER_KEYWORDS = (
    "lumber",
    "garris",
    "evans",
    "2x4",
    "2x6",
    "2x8",
    "2x10",
    "2x12",
    "plywood",
    "osb",
    "stud",
    "board",
    "treated",
    "pressure",
    "lowe",
    "menards",
    "home depot",
    "homedepot",
)

REGISTER_FIELDS = [
    "Date",
    "Supplier",
    "Item_Description",
    "Qty",
    "Unit",
    "Unit_Price",
    "Line_Total",
    "Job_Reference",
    "Receipt_File",
    "Logged_At",
    "Verified_By",
    "Notes",
]


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def correct_supplier_text(text: str) -> str:
    out = text
    for pattern, repl in SUPPLIER_CORRECTIONS:
        out = pattern.sub(repl.replace("_", " "), out)
    # Normalize display name for supplier field
    out = re.sub(r"Garris\s+Evans", "Garris Evans", out, flags=re.I)
    return out


def correct_filename(name: str) -> str:
    stem = Path(name).stem
    suffix = Path(name).suffix
    corrected = stem
    for pattern, repl in SUPPLIER_CORRECTIONS:
        corrected = pattern.sub(repl, corrected)
    return corrected + suffix


def is_lumber_receipt(name: str, extra_text: str = "") -> bool:
    blob = f"{name} {extra_text}".lower()
    return any(k in blob for k in LUMBER_KEYWORDS)


def _parse_hint_from_filename(name: str) -> Dict[str, str]:
    """Best-effort parse: YYYY-MM-DD_job_supplier_type_amount.ext"""
    hints: Dict[str, str] = {}
    stem = Path(name).stem
    m = re.match(r"(?P<date>\d{4}-\d{2}-\d{2})_(?P<rest>.+)", stem)
    if not m:
        return hints
    hints["date"] = m.group("date")
    parts = m.group("rest").split("_")
    if not parts:
        return hints
    hints["job"] = parts[0].replace("-", " ")
    # Last numeric token is often total amount
    if parts and re.match(r"^\d+(\.\d{1,2})?$", parts[-1].replace("$", "")):
        hints["amount"] = parts[-1].replace("$", "")
        parts = parts[:-1]
    blob = " ".join(parts).lower()
    if "lumber" in blob or "garris" in blob or re.search(r"\b2x\d", blob):
        hints["category"] = "lumber"
    if "garris" in blob or ("evans" in blob and "lumber" in blob):
        hints["supplier"] = "Garris Evans"
    elif len(parts) >= 2:
        hints["supplier"] = correct_supplier_text(parts[1].replace("-", " "))
    return hints


def _load_manifest(inbox: Path) -> Dict[str, Any]:
    path = inbox / MANIFEST_NAME
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"processed": {}}


def _save_manifest(inbox: Path, manifest: Dict[str, Any]) -> None:
    (inbox / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _ensure_register(workspace: Path) -> Path:
    reg = workspace / "08_Admin_Standards" / "LUMBER_PRICE_REGISTER.csv"
    if not reg.is_file():
        reg.parent.mkdir(parents=True, exist_ok=True)
        with reg.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(REGISTER_FIELDS)
    return reg


def _append_register_row(workspace: Path, row: Dict[str, str]) -> None:
    reg = _ensure_register(workspace)
    with reg.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REGISTER_FIELDS, extrasaction="ignore")
        w.writerow({k: row.get(k, "") for k in REGISTER_FIELDS})


def _write_readable_summaries(workspace: Path, report: Dict[str, Any]) -> List[str]:
    notes: List[str] = []
    readable = workspace / "00_START_HERE" / "READABLE"
    readable.mkdir(parents=True, exist_ok=True)

    log_path = readable / "RECEIPT_INTAKE_LOG.txt"
    lines = [f"[{_stamp()}] receipt intake", f"  processed={report.get('processed', 0)} lumber={report.get('lumber', 0)}"]
    for n in report.get("notes") or []:
        lines.append(f"  + {n}")
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n\n")
    notes.append("RECEIPT_INTAKE_LOG.txt updated")

    pending = report.get("pending_review") or []
    pending_path = readable / "PENDING_RECEIPT_REVIEW.txt"
    if pending:
        body = [
            "PENDING RECEIPT REVIEW — triple-check with Cursor",
            f"Updated: {_stamp()}",
            "",
            "Send these images to desktop Cursor for line-item analysis, then log/sync again.",
            "",
        ]
        body.extend(pending)
        pending_path.write_text("\n".join(body) + "\n", encoding="utf-8")
        notes.append(f"PENDING_RECEIPT_REVIEW.txt ({len(pending)} item(s))")
    elif pending_path.is_file():
        pending_path.write_text(
            f"No pending receipts — last check {_stamp()}\n", encoding="utf-8"
        )

    reg = workspace / "08_Admin_Standards" / "LUMBER_PRICE_REGISTER.csv"
    summary = readable / "LUMBER_PRICES_SUMMARY.txt"
    if reg.is_file():
        rows: List[dict] = []
        with reg.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        known = [r for r in rows if (r.get("Item_Description") or "").strip()]
        lines = [
            "J & R CONSTRUCTION — KNOWN LUMBER PRICES (summary)",
            f"Updated: {_stamp()}",
            f"Total logged line items: {len(known)}",
            "Supplier: Garris Evans (lumber) — NOT Gary Evans",
            "",
        ]
        for r in known[-25:]:
            lines.append(
                f"  {r.get('Date','')} | {r.get('Supplier','')} | {r.get('Item_Description','')} "
                f"| qty {r.get('Qty','')} @ ${r.get('Unit_Price','')} = ${r.get('Line_Total','')} "
                f"| job {r.get('Job_Reference','')}"
            )
        summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        notes.append(f"LUMBER_PRICES_SUMMARY.txt ({len(known)} items in register)")
    return notes


def process_receipt_inbox(workspace: Path) -> Dict[str, Any]:
    """Process new iPhone receipt drops during log/sync."""
    report: Dict[str, Any] = {
        "processed": 0,
        "lumber": 0,
        "notes": [],
        "pending_review": [],
        "errors": [],
    }
    inbox = workspace / INBOX_DIR
    inbox.mkdir(parents=True, exist_ok=True)
    readme = inbox / "Readme_drop_photos_here.txt"
    if not readme.is_file():
        src = Path(__file__).resolve().parents[1] / "scripts/templates/dropbox_workspace/02_RECEIPTS_PHOTO_INBOX/Readme_drop_photos_here.txt"
        if src.is_file():
            shutil.copy2(src, readme)

    manifest = _load_manifest(inbox)
    processed: Dict[str, str] = manifest.get("processed") or {}

    for src in sorted(inbox.iterdir()):
        if not src.is_file():
            continue
        if src.name.startswith(".") or src.name.lower() == "readme_drop_photos_here.txt":
            continue
        if src.suffix.lower() not in RECEIPT_EXTENSIONS:
            continue
        key = f"{src.name}:{src.stat().st_size}:{int(src.stat().st_mtime)}"
        if key in processed:
            continue

        corrected_name = correct_filename(src.name)
        hints = _parse_hint_from_filename(corrected_name)
        date_part = hints.get("date") or datetime.now().strftime("%Y-%m")
        month_dir = date_part[:7] if len(date_part) >= 7 else datetime.now().strftime("%Y-%m")
        filed_root = workspace / "06_Bookkeeping_Taxes" / "Receipts_Filed"
        dest_dir = filed_root / month_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / corrected_name
        if dest.exists():
            dest = dest_dir / f"{Path(corrected_name).stem}_{int(datetime.now().timestamp())}{Path(corrected_name).suffix}"
        shutil.copy2(src, dest)

        lumber = is_lumber_receipt(corrected_name, hints.get("category", ""))
        supplier = hints.get("supplier") or ("Garris Evans" if lumber and "garris" in corrected_name.lower() else "")
        if lumber and not supplier and "evans" in corrected_name.lower():
            supplier = "Garris Evans"

        if name_fixed := (corrected_name != src.name):
            report["notes"].append(f"corrected filename: {src.name} → {corrected_name}")

        rel_file = str(dest.relative_to(workspace))
        if lumber:
            report["lumber"] += 1
            amount = hints.get("amount", "")
            if amount:
                _append_register_row(
                    workspace,
                    {
                        "Date": hints.get("date", date_part[:10] if len(date_part) >= 10 else ""),
                        "Supplier": correct_supplier_text(supplier or "Garris Evans"),
                        "Item_Description": hints.get("category", "lumber materials"),
                        "Qty": "1",
                        "Unit": "lot",
                        "Unit_Price": amount,
                        "Line_Total": amount,
                        "Job_Reference": hints.get("job", ""),
                        "Receipt_File": rel_file,
                        "Logged_At": _stamp(),
                        "Verified_By": "auto-filename",
                        "Notes": "Triple-check line items in Cursor; update register after analysis",
                    },
                )
                report["notes"].append(f"lumber register row: {corrected_name} ${amount}")
            else:
                report["pending_review"].append(
                    f"- {rel_file} | lumber receipt | job={hints.get('job','?')} | NEEDS Cursor line-item analysis"
                )
        else:
            report["pending_review"].append(
                f"- {rel_file} | general receipt | job={hints.get('job','?')} | triple-check amount + job"
            )

        processed[key] = str(dest)
        report["processed"] += 1
        report["notes"].append(f"filed: {rel_file}")

    manifest["processed"] = processed
    manifest["last_run"] = _stamp()
    _save_manifest(inbox, manifest)
    report["notes"].extend(_write_readable_summaries(workspace, report))
    return report


def main(argv: Optional[List[str]] = None) -> int:
    import sys

    from app.jrc_workspace import resolve_workspace

    args = list(argv if argv is not None else sys.argv[1:])
    base = resolve_workspace()
    if not base:
        print("Workspace not found")
        return 1
    rep = process_receipt_inbox(base)
    print(json.dumps(rep, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
