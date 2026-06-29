#!/usr/bin/env python3
"""Find and open a job quote/estimate from the active jobs registry."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
REGISTRY = BASE_DIR / "business_standards" / "JRC_Active_Jobs_Registry.json"
REJECT_PATTERNS = (
    r"chain[- ]?link",
    r"generate_lily_315_fence_estimate",
    r"EST-JRC-JOB-315-LILY-FENCE-001",
)
SEARCH_DIRS = [
    BASE_DIR / "docs" / "quotes",
    BASE_DIR / "docs" / "internal",
    BASE_DIR / "exports",
    BASE_DIR / "iphone_files",
    BASE_DIR / "evidence",
    BASE_DIR / "dropbox_business",
]
DROPBOX_CANDIDATES = [
    Path.home() / "Dropbox",
    Path.home() / "OneDrive" / "Desktop",
    Path.home() / "Documents",
]
DOC_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".html", ".htm"}


def load_registry() -> dict:
    if not REGISTRY.is_file():
        raise SystemExit(f"Missing registry: {REGISTRY}")
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def is_rejected(path: Path, job: dict) -> bool:
    blob = f"{path.name} {path}".lower()
    for pattern in job.get("invalid_reject", []):
        if pattern.lower() in blob:
            return True
    for pattern in REJECT_PATTERNS:
        if re.search(pattern, blob, re.I):
            return True
    return False


def score_match(query: str, job: dict) -> int:
    q = normalize(query)
    score = 0
    tokens = [
        job.get("job_id", ""),
        job.get("customer_name", ""),
        job.get("address", ""),
        job.get("scope", ""),
        *job.get("customer_aliases", []),
    ]
    blob = normalize(" ".join(tokens))
    for word in q.split():
        if len(word) < 2:
            continue
        if word in blob:
            score += 3
    if "315" in q and "315" in blob:
        score += 4
    if "sassafras" in q and "sassafras" in blob:
        score += 4
    if "fence" in q and "fence" in blob:
        score += 4
    if any(alias.lower() in q for alias in job.get("customer_aliases", [])):
        score += 3
    return score


def find_job(query: str, registry: dict) -> dict | None:
    best = None
    best_score = 0
    for job in registry.get("jobs", []):
        score = score_match(query, job)
        if score > best_score:
            best_score = score
            best = job
    return best if best_score >= 4 else None


def candidate_roots(job: dict) -> list[Path]:
    roots = list(SEARCH_DIRS)
    folder = (job.get("document_folder") or "").strip()
    env_root = os.environ.get("JRC_DROPBOX_FOLDER", "").strip()
    if env_root:
        roots.append(Path(env_root).expanduser())
    for parent in DROPBOX_CANDIDATES:
        if parent.exists():
            roots.append(parent)
            if folder:
                roots.append(parent / folder)
    legacy = ["Invoices2026 1.0", "J and R Construction", "JRC"]
    for legacy_name in legacy:
        for parent in DROPBOX_CANDIDATES:
            candidate = parent / legacy_name
            if candidate.exists():
                roots.append(candidate)
                if folder:
                    roots.append(candidate / folder)
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def quote_keywords(job: dict) -> tuple[str, ...]:
    words = ("quote", "estimate", "est-", "inv-", "invoice", "fence", "dog", "ear")
    scope = (job.get("scope") or "").lower()
    if "stair" in scope:
        words = ("quote", "estimate", "est-", "inv-", "invoice", "stair")
    return words


def search_quote(job: dict) -> tuple[Path | None, list[str]]:
    searched: list[str] = []
    hits: list[tuple[int, Path]] = []
    keywords = quote_keywords(job)
    aliases = [a.lower() for a in job.get("customer_aliases", [])]
    aliases.append((job.get("customer_name") or "").split()[0].lower())

    for root in candidate_roots(job):
        searched.append(str(root))
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in DOC_EXTENSIONS:
                continue
            if is_rejected(path, job):
                continue
            name = path.name.lower()
            score = 0
            if any(k in name for k in keywords):
                score += 2
            if "315" in name or "sassafras" in name:
                score += 2
            if any(a and a in name for a in aliases):
                score += 2
            if "stair" in name and "fence" in (job.get("scope") or "").lower():
                score -= 4
            if "fence" in name and "stair" in (job.get("scope") or "").lower():
                score -= 4
            if score >= 4:
                hits.append((score, path))

    if not hits:
        return None, searched
    hits.sort(key=lambda item: (-item[0], -item[1].stat().st_mtime))
    return hits[0][1], searched


def open_path(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def main() -> int:
    query = " ".join(sys.argv[1:]).strip() or "315 sassafras lily fence"
    registry = load_registry()
    job = find_job(query, registry)
    if not job:
        print(f"No registry match for: {query}")
        return 1

    print(f"Job: {job['job_id']}")
    print(f"Customer: {job.get('customer_name')} ({', '.join(job.get('customer_aliases', []))})")
    print(f"Address: {job.get('address')}")
    print(f"Scope: {job.get('scope')}")
    print(f"Status: {job.get('status')}")

    quote, searched = search_quote(job)
    if quote:
        print(f"\nFound quote: {quote}")
        try:
            open_path(quote)
            print("Opened file.")
        except Exception as exc:
            print(f"Could not auto-open ({exc}). Path above is the file location.")
        return 0

    record = BASE_DIR / "docs" / "internal" / "lillian-315-sassafras-dogear-fence" / "JOB_RECORD.txt"
    print("\nQuote file not found in this workspace.")
    print("Searched:")
    for path in searched:
        print(f"  - {path}")
    if record.is_file():
        print(f"\nSee internal record: {record}")
    print(
        "\nSync from PC Cursor or Dropbox into:\n"
        "  docs/quotes/lillian-315-sassafras/\n"
        "  docs/internal/lillian-315-sassafras-dogear-fence/"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
