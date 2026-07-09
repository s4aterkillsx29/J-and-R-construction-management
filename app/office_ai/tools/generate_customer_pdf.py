# -*- coding: utf-8 -*-
"""Customer PDF generation preview (approval required)."""
from __future__ import annotations

from app.office_ai.tools.base import find_job_folder


def preview(*, job_code: str = "", document_type: str = "customer_invoice", description: str = "", **kwargs) -> dict:
    if not job_code:
        return {"ok": False, "error": "job_code required"}
    folder = find_job_folder(job_code)
    if not folder:
        return {"ok": False, "error": f"Job folder not found for {job_code}"}
    preview_text = (
        f"Would generate {document_type} for {job_code}\n"
        f"Job folder: {folder}\n"
        f"Description: {description or '(from job workup)'}\n\n"
        "Uses tools/jrc_official_documents.py standards after approval.\n"
        "Output folder: dropbox-records/02_Documents_Invoices_Estimates_Quotes/"
    )
    return {
        "ok": True,
        "preview_text": preview_text,
        "job_code": job_code,
        "document_type": document_type,
        "job_folder": str(folder),
    }


def execute(*, job_code: str = "", document_type: str = "customer_invoice", description: str = "", **kwargs) -> dict:
    info = preview(job_code=job_code, document_type=document_type, description=description)
    if not info.get("ok"):
        return info
    folder = find_job_folder(job_code)
    doc_map = {
        "customer_invoice": "invoice",
        "customer_quote": "quote",
        "internal_workup": "quote",
    }
    doc_type = doc_map.get(document_type, "invoice")
    from app.pdf_bridge import build_customer_pdf

    result = build_customer_pdf(
        job_code=job_code,
        doc_type=doc_type,
        output_dir=folder,
        description=description,
    )
    if not result.get("ok"):
        return result
    return {
        "ok": True,
        "message": result.get("message", f"PDF built for {job_code}"),
        "job_folder": str(folder) if folder else result.get("output_dir", ""),
        "output_dir": result.get("output_dir", ""),
        "files": result.get("files", []),
    }


def run(**kwargs) -> dict:
    return preview(**kwargs)


SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_customer_pdf",
        "description": "Request customer/internal PDF generation for a job (requires owner approval before run).",
        "parameters": {
            "type": "object",
            "properties": {
                "job_code": {"type": "string"},
                "document_type": {"type": "string", "enum": ["customer_invoice", "customer_quote", "internal_workup"]},
                "description": {"type": "string"},
            },
            "required": ["job_code"],
        },
    },
}
