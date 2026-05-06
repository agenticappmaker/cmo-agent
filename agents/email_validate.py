"""
Layered email validator for outreach pre-send.

Tier 1 (free, always on): regex + DNS MX lookup. Catches typos and dead domains.
Tier 2 (paid, optional):  Abstract API risk scoring. Enabled when ABSTRACT_API_KEY set.

Verdicts:
    ok            -> send normally
    risky         -> send (still likely deliverable; flag in caller)
    undeliverable -> drop from outbox

Free-first: Abstract is best-effort. Tier 1 always runs first.
"""

from __future__ import annotations

import json
import os
import re
import socket
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import URLError

try:
    import dns.resolver  # type: ignore
    HAS_DNSPYTHON = True
except ImportError:
    HAS_DNSPYTHON = False

RFC_LITE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

DOMAIN_TYPOS = {
    "gmial.com": "gmail.com",
    "gmai.com": "gmail.com",
    "gnail.com": "gmail.com",
    "gmail.con": "gmail.com",
    "gmail.co": "gmail.com",
    "yaho.com": "yahoo.com",
    "yahooo.com": "yahoo.com",
    "yahoo.con": "yahoo.com",
    "hotmial.com": "hotmail.com",
    "hotmail.con": "hotmail.com",
    "outlok.com": "outlook.com",
}

ROLE_LOCALS = {
    "admin", "info", "support", "sales", "contact", "help", "noreply", "no-reply",
    "postmaster", "webmaster", "abuse", "hostmaster",
}


@dataclass
class EmailVerdict:
    ok: bool
    risky: bool
    reason: Optional[str]
    suggestion: Optional[str]
    source: str  # regex | dns | abstract


def _has_mx(domain: str, timeout: float = 3.0) -> bool:
    """Cheap MX existence check. Uses dnspython if available, else falls back to
    socket-based A/AAAA lookup as a soft proof-of-life."""
    if HAS_DNSPYTHON:
        try:
            resolver = dns.resolver.Resolver()
            resolver.lifetime = timeout
            answers = resolver.resolve(domain, "MX")
            return len(answers) > 0
        except Exception:
            return False
    # No dnspython: any A/AAAA record means SOMETHING answers; weak but better than nothing.
    try:
        socket.gethostbyname(domain)
        return True
    except OSError:
        return False


def validate_email(raw: str) -> EmailVerdict:
    email = (raw or "").strip().lower()
    if not email or not RFC_LITE.match(email):
        return EmailVerdict(False, False, "invalid format", None, "regex")

    try:
        local, domain = email.split("@", 1)
    except ValueError:
        return EmailVerdict(False, False, "invalid format", None, "regex")

    fixed = DOMAIN_TYPOS.get(domain)
    if fixed:
        return EmailVerdict(False, False, f"typo: meant {local}@{fixed}?", f"{local}@{fixed}", "regex")

    if not _has_mx(domain):
        return EmailVerdict(False, False, "no mail server for domain", None, "dns")

    risky = local in ROLE_LOCALS
    reason = "role address" if risky else None

    api_key = os.environ.get("ABSTRACT_API_KEY")
    if api_key:
        try:
            url = (
                "https://emailreputation.abstractapi.com/v1/"
                f"?api_key={api_key}&email={quote(email)}"
            )
            req = Request(url, headers={"User-Agent": "smore-outreach"})
            with urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            deliverability = data.get("email_deliverability") or {}
            quality = data.get("email_quality") or {}
            risk = data.get("email_risk") or {}
            status = deliverability.get("status")
            score = quality.get("score")
            disposable = quality.get("is_disposable")
            suspicious = quality.get("is_username_suspicious")
            address_risk = risk.get("address_risk_status")
            domain_risk = risk.get("domain_risk_status")

            if status == "undeliverable":
                return EmailVerdict(False, False, "abstract: undeliverable", None, "abstract")
            if address_risk == "high" or domain_risk == "high":
                return EmailVerdict(False, False, "abstract: high risk", None, "abstract")
            if disposable:
                risky = True
                reason = "disposable address"
            if suspicious:
                risky = True
                reason = reason or "suspicious username"
            if isinstance(score, (int, float)) and score < 0.3:
                risky = True
                reason = reason or "low quality score"
        except (URLError, OSError, ValueError, KeyError):
            # Best-effort. Tier 1 already passed.
            pass

    return EmailVerdict(True, risky, reason, None, "abstract" if risky else "dns")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python email_validate.py <email>")
        sys.exit(1)
    v = validate_email(sys.argv[1])
    print(json.dumps(v.__dict__, indent=2))
