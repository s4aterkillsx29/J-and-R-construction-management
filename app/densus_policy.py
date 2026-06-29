"""Densus password policy — shared with J & R Construction Manager (admin tools)."""
from __future__ import annotations

import hashlib
import math
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

FORBIDDEN_PASSWORDS = frozenset({
    "ivygrows", "admin", "admin123", "password", "admin/admin",
    "jandr", "jrconstruction", "jandrconstruction", "j&rconstruction",
    "12345678", "123456789", "qwerty123", "letmein1", "welcome1",
})

MIN_PASSWORD_LENGTH = 8
MIN_PASSWORD_ENTROPY = 2.75

COMMON_PATTERNS = [
    (r"^(.)\1{4,}", "Too many repeated characters"),
    (r"^(012|123|234|345|456|567|678|789|890)+", "Sequential numbers"),
    (r"(password|admin|jandr|construction|ivygrows)", "Contains forbidden word"),
]


@dataclass
class PolicyProfile:
    key: str
    label: str
    min_length: int
    require_upper: bool
    require_lower: bool
    require_digit: bool
    require_symbol: bool
    min_entropy: float
    forbid_defaults: bool
    description: str


POLICY_PROFILES: Dict[str, PolicyProfile] = {
    "standard": PolicyProfile(
        "standard", "Standard Account", MIN_PASSWORD_LENGTH, True, True, True, False, MIN_PASSWORD_ENTROPY, True,
        "Workers, viewers, general staff.",
    ),
    "owner": PolicyProfile(
        "owner", "Owner / Admin (JRC)", MIN_PASSWORD_LENGTH, True, True, True, False, MIN_PASSWORD_ENTROPY, True,
        "Jacob / owner accounts — min 8 chars, upper/lower/digit, symbols optional.",
    ),
    "cloud": PolicyProfile(
        "cloud", "Cloud / Public Host", MIN_PASSWORD_LENGTH, True, True, True, False, MIN_PASSWORD_ENTROPY, True,
        "Internet-facing and cloud deploy passwords.",
    ),
    "customer": PolicyProfile(
        "customer", "Customer Portal", MIN_PASSWORD_LENGTH, True, True, True, False, MIN_PASSWORD_ENTROPY, True,
        "Customer-facing portal accounts.",
    ),
    "paranoid": PolicyProfile(
        "paranoid", "Paranoid / Maximum", MIN_PASSWORD_LENGTH, True, True, True, False, MIN_PASSWORD_ENTROPY, True,
        "Maximum strictness — financial and mastery-adjacent secrets.",
    ),
    "mastery_adjacent": PolicyProfile(
        "mastery_adjacent", "Emergency Key Adjacent", MIN_PASSWORD_LENGTH, True, True, True, False, MIN_PASSWORD_ENTROPY, True,
        "Must not resemble first-setup or mastery-style passwords.",
    ),
}


_POLICY_FILE = Path(__file__)
_RULES_CACHE: tuple[int, float] | None = None
_RULES_MTIME: float = -1.0


def live_password_rules() -> tuple[int, float]:
    """Read length/entropy constants from disk so a running host picks up policy file edits."""
    global _RULES_CACHE, _RULES_MTIME
    try:
        mtime = _POLICY_FILE.stat().st_mtime
        if _RULES_CACHE is not None and mtime == _RULES_MTIME:
            return _RULES_CACHE
        text = _POLICY_FILE.read_text(encoding="utf-8")
        m_len = re.search(r"^MIN_PASSWORD_LENGTH\s*=\s*(\d+)", text, re.M)
        m_ent = re.search(r"^MIN_PASSWORD_ENTROPY\s*=\s*([\d.]+)", text, re.M)
        min_len = int(m_len.group(1)) if m_len else MIN_PASSWORD_LENGTH
        min_ent = float(m_ent.group(1)) if m_ent else MIN_PASSWORD_ENTROPY
        _RULES_CACHE = (min_len, min_ent)
        _RULES_MTIME = mtime
        return _RULES_CACHE
    except Exception:
        return MIN_PASSWORD_LENGTH, MIN_PASSWORD_ENTROPY


def active_profile(profile: PolicyProfile) -> PolicyProfile:
    """Apply current on-disk rules; symbols stay optional for all roles."""
    min_len, min_ent = live_password_rules()
    return PolicyProfile(
        profile.key,
        profile.label,
        min_len,
        profile.require_upper,
        profile.require_lower,
        profile.require_digit,
        False,
        min_ent,
        profile.forbid_defaults,
        profile.description,
    )


def shannon_entropy(password: str) -> float:
    if not password:
        return 0.0
    freq: Dict[str, int] = {}
    for ch in password:
        freq[ch] = freq.get(ch, 0) + 1
    length = len(password)
    return -sum((c / length) * math.log2(c / length) for c in freq.values())


def score_strength(password: str) -> Tuple[int, str]:
    if not password:
        return 0, "Empty"
    ent = shannon_entropy(password)
    length = len(password)
    variety = sum([
        bool(re.search(r"[A-Z]", password)),
        bool(re.search(r"[a-z]", password)),
        bool(re.search(r"\d", password)),
        bool(re.search(r"[^A-Za-z0-9]", password)),
    ])
    score = min(100, int(length * 3 + ent * 12 + variety * 8))
    if password.lower().strip() in FORBIDDEN_PASSWORDS:
        score = min(score, 15)
    if score >= 85:
        label = "Excellent"
    elif score >= 70:
        label = "Strong"
    elif score >= 50:
        label = "Fair"
    elif score >= 30:
        label = "Weak"
    else:
        label = "Rejected"
    return score, label


@dataclass
class CheckResult:
    profile_key: str
    profile_label: str
    passed: bool
    score: int
    strength_label: str
    entropy: float
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def check_password_against_policy(password: str, profile: PolicyProfile) -> CheckResult:
    profile = active_profile(profile)
    issues: List[str] = []
    warnings: List[str] = []
    pw = password or ""
    if len(pw) < profile.min_length:
        issues.append(f"Minimum length is {profile.min_length} (got {len(pw)}).")
    if profile.require_upper and not re.search(r"[A-Z]", pw):
        issues.append("Needs at least one uppercase letter.")
    if profile.require_lower and not re.search(r"[a-z]", pw):
        issues.append("Needs at least one lowercase letter.")
    if profile.require_digit and not re.search(r"\d", pw):
        issues.append("Needs at least one digit.")
    if profile.require_symbol and not re.search(r"[^A-Za-z0-9]", pw):
        issues.append("Needs at least one symbol.")
    ent = shannon_entropy(pw)
    if ent < profile.min_entropy:
        issues.append(f"Entropy too low ({ent:.2f} < {profile.min_entropy}).")
    if profile.forbid_defaults and pw.lower().strip() in FORBIDDEN_PASSWORDS:
        issues.append("Matches a forbidden default/common password.")
    for pattern, msg in COMMON_PATTERNS:
        if re.search(pattern, pw, re.I):
            warnings.append(msg)
    if pw.lower() == "ivygrows1" or pw.lower().startswith("ivygrow"):
        issues.append("Too similar to reserved owner/mastery patterns.")
    score, strength_label = score_strength(pw)
    passed = len(issues) == 0 and score >= 50
    return CheckResult(
        profile.key, profile.label, passed, score, strength_label, ent, issues, warnings
    )


def multi_platform_check(password: str, profile_keys: Optional[List[str]] = None) -> List[CheckResult]:
    keys = profile_keys or list(POLICY_PROFILES.keys())
    return [check_password_against_policy(password, POLICY_PROFILES[k]) for k in keys if k in POLICY_PROFILES]


def suggest_strong_password(length: int = 16) -> str:
    length = max(MIN_PASSWORD_LENGTH, min(64, length))
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789!@#$%&*"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        r = check_password_against_policy(pw, POLICY_PROFILES["owner"])
        if r.passed:
            return pw


def fingerprint_for_log(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()[:12]


def profile_for_jrc_role(role: str) -> str:
    role = (role or "worker").lower()
    if role == "admin":
        return "owner"
    if role == "customer":
        return "customer"
    if role in ("manager",):
        return "standard"
    return "standard"


def password_policy_summary() -> str:
    min_len, _ = live_password_rules()
    return (
        f"At least {min_len} characters with uppercase, lowercase, and a number. "
        "Symbols are optional."
    )


def enforce_densus_password(password: str, role: str = "worker") -> Tuple[bool, str]:
    profile_key = profile_for_jrc_role(role)
    result = check_password_against_policy(password, POLICY_PROFILES[profile_key])
    if result.passed:
        return True, "OK"
    if result.issues:
        return False, result.issues[0]
    return False, f"Password too weak ({result.strength_label}). Use a longer, unique password."


def format_results_html(password: str, results: List[CheckResult]) -> str:
    import html as html_mod
    lines = []
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        color = "ok" if r.passed else "red"
        lines.append(
            f"<p><span class='badge {color}'>{status}</span> "
            f"<b>{html_mod.escape(r.profile_label)}</b> — {r.score}/100 ({html_mod.escape(r.strength_label)})</p>"
        )
        for i in r.issues:
            lines.append(f"<p class='muted'>✗ {html_mod.escape(i)}</p>")
        for w in r.warnings:
            lines.append(f"<p class='muted'>! {html_mod.escape(w)}</p>")
    return "".join(lines)
