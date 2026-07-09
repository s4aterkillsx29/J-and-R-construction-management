# -*- coding: utf-8 -*-
"""Build quote/invoice PDF package via pdf_bridge (approval required)."""
from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "build_quote_package",
        "description": "Build customer PDF package for a job via official document builder.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_code": {"type": "string"},
                "doc_type": {"type": "string", "enum": ["invoice", "quote", "proposal"], "default": "quote"},
            },
            "required": ["job_code"],
        },
    },
}


def preview(*, job_code: str, doc_type: str = "quote", **kwargs) -> dict:
    text = (
        f"Will build {doc_type} PDF package for {job_code} via jrc_official_documents.py\n"
        f"Output copies to exports + JRC_PRINT when approved."
    )
    return {"ok": True, "preview_text": text}


def run(*, job_code: str, doc_type: str = "quote", **kwargs) -> dict:
    from app.pdf_bridge import build_customer_pdf

    result = build_customer_pdf(job_code=job_code, doc_type=doc_type)
    if not result.get("ok"):
        return result
    print_dir = __import__("pathlib").Path.home() / "Dropbox" / "JRC_PRINT"
    result["jrc_print_dir"] = str(print_dir)
    result["preview_text"] = result.get("message", "PDF built") + f" → {result.get('output_dir', '')}"
    return result
