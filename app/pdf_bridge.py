# -*- coding: utf-8 -*-
"""Bridge to tools/jrc_official_documents.py for customer PDF packages."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

BASE_DIR = Path(__file__).resolve().parents[1]


def _import_jrc_documents():
    from app.program_paths import assert_bridge_allowed, tools_root

    assert_bridge_allowed("pdf_bridge")
    tools = tools_root()
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import jrc_official_documents  # type: ignore

    return jrc_official_documents, tools


def _minimal_config(job_code: str, doc_type: str, customer_name: str = "Customer") -> Any:
    jrc, _ = _import_jrc_documents()
    total = 1000.0
    deposit_pct = 50 if doc_type == "invoice" else 70
    balance_pct = 100 - deposit_pct
    deposit = round(total * deposit_pct / 100, 2)
    balance = round(total - deposit, 2)
    title_map = {
        "invoice": "Customer Invoice",
        "quote": "Customer Estimate",
        "proposal": "Customer Proposal",
    }
    return jrc.JobDocumentConfig(
        job_code=job_code,
        document_date=datetime.now().strftime("%Y-%m-%d"),
        customer_name=customer_name,
        customer_address_lines=["Address on file"],
        job_site_line="Job site per workup",
        scope_title=f"Scope — {job_code}",
        scope_summary=f"Official {doc_type} package for {job_code}",
        scope_rows=[("Work scope", "Per internal workup")],
        customer_total=total,
        deposit=deposit,
        balance=balance,
        deposit_pct=deposit_pct,
        balance_pct=balance_pct,
        customer_doc_title=title_map.get(doc_type, "Customer Estimate"),
        omit_customer_pricing=(doc_type == "proposal"),
        footer_status="Generated via JRC Manager pdf_bridge",
    )


def build_customer_pdf(
    *,
    job_code: str,
    doc_type: str = "invoice",
    output_dir: Optional[Path] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Build customer + internal PDFs via direct import of jrc_official_documents."""
    if not job_code:
        return {"ok": False, "error": "job_code required"}
    try:
        jrc, tools = _import_jrc_documents()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    customer_name = str(kwargs.get("customer_name") or "Customer")
    cfg = _minimal_config(job_code, doc_type, customer_name)

    job_folder = output_dir
    if job_folder is None:
        try:
            from app.office_ai.tools.base import find_job_folder

            job_folder = find_job_folder(job_code)
        except Exception:
            job_folder = None
    if job_folder is None:
        job_folder = BASE_DIR / "exports" / job_code.replace("/", "_")
    job_folder = Path(job_folder)
    job_folder.mkdir(parents=True, exist_ok=True)
    docs_folder = job_folder / "02_Documents_Invoices_Estimates_Quotes"
    docs_folder.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d")
    slug = job_code.replace("JRC-", "JRC-")
    customer_file = f"{stamp}__{slug}__Customer_{doc_type.title()}.pdf"
    internal_file = f"{stamp}__{slug}__Internal_Workup.pdf"

    builders = {
        customer_file: lambda p, c=cfg, d=doc_type: jrc.build_customer_estimate_pdf(p, c)
        if d != "proposal"
        else jrc.build_customer_estimate_pdf(p, c),
        internal_file: lambda p, c=cfg: jrc.build_internal_workup_pdf(p, c),
    }
    print_names = {customer_file: customer_file}

    try:
        jrc.publish_job_pdfs(
            str(job_folder),
            str(docs_folder),
            builders,
            print_names=print_names,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "message": f"PDF package built for {job_code}",
        "output_dir": str(job_folder),
        "docs_folder": str(docs_folder),
        "tools_root": str(tools),
        "files": [customer_file, internal_file],
    }
