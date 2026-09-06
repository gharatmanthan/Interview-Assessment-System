"""
Canonical email validation and normalization.

Single source of truth for every email entering the system: API forms,
JSON bodies, email-intake sender addresses. The rule accepts standard
addresses including plus-tags (`name+jobs@domain.com`), subdomains,
and dotted local parts, while rejecting clearly malformed inputs.

Normalization (trim whitespace, lowercase) must be applied wherever an
email is stored or compared so that duplicate detection and lookups on
(email, job_id) behave consistently regardless of how the user typed it.
"""
import re

# Local part: one or more dot-separated atoms; each atom is at least one
# RFC-5322 atom character. No consecutive dots, no leading/trailing dot.
_LOCAL_ATOM = r"[A-Za-z0-9!#$%&'*+\-/=?^_`{|}~]+"
_LOCAL_PART = _LOCAL_ATOM + r"(?:\." + _LOCAL_ATOM + r")*"

# Domain: one or more labels separated by dots. Each label starts and ends
# with an alnum character, may contain hyphens internally, and must be
# 1-63 characters. At least two labels required (rejects bare `user@domain`).
_DOMAIN_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_DOMAIN = _DOMAIN_LABEL + r"(?:\." + _DOMAIN_LABEL + r")+"

EMAIL_RE = re.compile(r"^" + _LOCAL_PART + r"@" + _DOMAIN + r"$")


def normalize_email(value: str) -> str:
    """Trim whitespace and lowercase."""
    return (value or "").strip().lower()


def is_valid_email(value: str) -> bool:
    """Return True if *value* is a plausible email address.

    This deliberately avoids being overly restrictive: it accepts
    plus-tags, dotted local parts, and multi-part domains while
    rejecting addresses missing an ``@``, empty local/domain parts,
    consecutive dots, trailing dots, and TLDs without a dot.
    """
    if not isinstance(value, str):
        return False
    s = value.strip()
    if not s or len(s) > 254 or " " in s or "@" not in s:
        return False
    return bool(EMAIL_RE.match(s))
