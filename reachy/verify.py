"""Email verification with explicit, non-fabricated states.

Definitions used by Reachy:

``valid``       Explicitly published address (mailto, JSON-LD, decoded Cloudflare
                protection, or a crawl) on a domain that publishes MX records.
                This verifies the *domain*, not that the individual mailbox exists.
``invalid``     Bad syntax, null MX, or no MX/A record.
``catch_all``   Only when the operator explicitly enables the SMTP probe and the
                domain accepts arbitrary recipients.
``unknown``     DNS was unavailable/transient, or only an A record exists.
``unverified`` No verification has been attempted.

Reachy never guesses an address and never labels a guessed address as verified.
"""

from __future__ import annotations

import random
import smtplib
import string
from dataclasses import dataclass
from typing import Optional, Protocol

from .db import Database, utcnow
from .models import VerificationResult
from .normalize import email_domain, is_valid_email_syntax, normalize_email

EXPLICIT_DISCOVERY_METHODS = {
    "lead_email_field",
    "website_crawl",
    "structured_data",
    "cloudflare_protected",
    "manual",
    "csv_import",
    "api",
}


class DNSBackend(Protocol):
    def mx(self, domain: str) -> list[str]:
        ...

    def a_exists(self, domain: str) -> bool:
        ...


class DnspythonBackend:
    def __init__(self, lifetime: float = 4.0):
        self.lifetime = lifetime

    def mx(self, domain: str) -> list[str]:
        import dns.resolver

        try:
            answers = dns.resolver.resolve(domain, "MX", lifetime=self.lifetime)
        except Exception as exc:  # noqa: BLE001 - surfaced as unknown by caller
            if exc.__class__.__name__ in {"NXDOMAIN", "NoAnswer"}:
                return []
            raise
        records = []
        for answer in answers:
            exchange = str(answer.exchange).rstrip(".").lower()
            records.append(exchange)
        return records

    def a_exists(self, domain: str) -> bool:
        import dns.resolver

        try:
            dns.resolver.resolve(domain, "A", lifetime=self.lifetime)
            return True
        except Exception:
            return False


@dataclass
class VerificationPolicy:
    allow_catch_all: bool = False
    smtp_probe_enabled: bool = False
    probe_from_address: str = "postmaster@example.com"

    def status_sendable(self, status: str) -> bool:
        if status == "valid":
            return True
        if status == "catch_all" and self.allow_catch_all:
            return True
        return False


def classify_domain(email: str, backend: Optional[DNSBackend] = None) -> VerificationResult:
    backend = backend or DnspythonBackend()
    normalized = normalize_email(email)
    if not is_valid_email_syntax(normalized):
        return VerificationResult("invalid", "syntax", "Address does not match email syntax", utcnow())
    domain = email_domain(normalized)
    assert domain
    try:
        mx_records = backend.mx(domain)
    except Exception as exc:  # noqa: BLE001
        return VerificationResult("unknown", "dns_mx", f"DNS lookup failed: {exc.__class__.__name__}", utcnow())
    if mx_records and any(record in {"", "."} for record in mx_records):
        return VerificationResult("invalid", "null_mx", "Domain publishes a null MX record", utcnow())
    if mx_records:
        return VerificationResult(
            "valid", "dns_mx", f"Published address; MX: {', '.join(mx_records[:3])}", utcnow()
        )
    try:
        has_a = backend.a_exists(domain)
    except Exception:
        has_a = False
    if has_a:
        return VerificationResult(
            "unknown", "dns_a_only", "No MX record; A record exists (mail delivery unconfirmed)", utcnow()
        )
    return VerificationResult("invalid", "dns_mx", "Domain has no MX record", utcnow())


def probe_catch_all(
    email: str,
    backend: Optional[DNSBackend] = None,
    from_address: str = "postmaster@example.com",
    timeout: float = 8.0,
) -> Optional[bool]:
    """Return True if the domain accepts an arbitrary recipient.

    This is disabled by default because it is intrusive and frequently blocked.
    Reachy never sends DATA during the probe. ``None`` means inconclusive.
    """
    backend = backend or DnspythonBackend()
    domain = email_domain(normalize_email(email))
    if not domain:
        return None
    try:
        mx_hosts = backend.mx(domain)
    except Exception:
        return None
    if not mx_hosts:
        return None
    rng = random.SystemRandom()
    fake_local = "reachy-probe-" + "".join(rng.choice(string.ascii_lowercase) for _ in range(12))
    fake = f"{fake_local}@{domain}"
    for host in mx_hosts[:2]:
        try:
            with smtplib.SMTP(host, 25, timeout=timeout) as smtp:
                smtp.ehlo_or_helo_if_needed()
                smtp.mail(from_address)
                code, _ = smtp.rcpt(fake)
            if code in (250, 251, 252):
                return True
            if 500 <= code < 600:
                return False
        except Exception:
            continue
    return None


def verify_email(
    email: str,
    discovery_method: str = "website_crawl",
    backend: Optional[DNSBackend] = None,
    policy: Optional[VerificationPolicy] = None,
) -> VerificationResult:
    policy = policy or VerificationPolicy()
    if discovery_method not in EXPLICIT_DISCOVERY_METHODS:
        return VerificationResult(
            "unverified", "not_explicit", "Address was not explicitly published by the business", utcnow()
        )
    result = classify_domain(email, backend=backend)
    if result.status == "valid" and policy.smtp_probe_enabled:
        catch_all = probe_catch_all(email, backend=backend, from_address=policy.probe_from_address)
        if catch_all is True:
            return VerificationResult("catch_all", "smtp_probe", "Domain accepts arbitrary recipients", utcnow())
    return result


def verify_contact(
    db: Database,
    contact_id: int,
    backend: Optional[DNSBackend] = None,
    policy: Optional[VerificationPolicy] = None,
    actor: str = "verifier",
) -> VerificationResult:
    row = db.fetchone("SELECT * FROM contacts WHERE id = ?", (contact_id,))
    if not row:
        raise KeyError(f"contact {contact_id} not found")
    result = verify_email(row["email"], row["discovery_method"], backend=backend, policy=policy)
    db.execute(
        """UPDATE contacts SET verification_status=?, verification_method=?, verification_detail=?,
               verified_at=?, updated_at=? WHERE id=?""",
        (result.status, result.method, result.detail, result.checked_at, utcnow(), contact_id),
    )
    db.audit(actor, "contact.verified", "contact", contact_id, {"status": result.status, "method": result.method})
    return result


def verify_contacts(
    db: Database,
    lead_id: Optional[int] = None,
    backend: Optional[DNSBackend] = None,
    policy: Optional[VerificationPolicy] = None,
    actor: str = "verifier",
) -> dict[str, int]:
    if lead_id is not None:
        rows = db.fetchall("SELECT id FROM contacts WHERE lead_id = ? ORDER BY id", (lead_id,))
    else:
        rows = db.fetchall("SELECT id FROM contacts ORDER BY id")
    counts: dict[str, int] = {}
    for row in rows:
        result = verify_contact(db, int(row["id"]), backend=backend, policy=policy, actor=actor)
        counts[result.status] = counts.get(result.status, 0) + 1
    return counts
