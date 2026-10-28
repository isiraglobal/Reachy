"""Lead/contact normalization, provenance, and deduplication."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from .db import Database, utcnow

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_PLACE_RE = re.compile(r"!1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)")
_CID_RE = re.compile(r"!19s([A-Za-z0-9_\-]+)")
_STATE_RE = re.compile(r"\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\b")
_CITY_STATE_RE = re.compile(r",\s*([^,]+),\s*([A-Z]{2})(?:\s+\d{5})?(?:,|\s|$)")

FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "icloud.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
}


def clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def normalize_email(value: str) -> str:
    text = (value or "").strip()
    if text.lower().startswith("mailto:"):
        text = text[7:]
    text = text.split("?", 1)[0].strip().strip("<>").lower()
    return text


def is_valid_email_syntax(value: str) -> bool:
    return bool(_EMAIL_RE.match(normalize_email(value)))


def email_domain(value: str) -> Optional[str]:
    normalized = normalize_email(value)
    return normalized.split("@", 1)[1] if "@" in normalized else None


def normalize_phone(value: Any) -> Optional[str]:
    if not value:
        return None
    raw = str(value)
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"+1 ({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if 7 <= len(digits) <= 15 and raw.strip().startswith("+"):
        return f"+{digits}"
    if 7 <= len(digits) <= 10:
        return digits
    return None


def normalize_domain(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    candidate = url.strip()
    if not candidate.startswith(("http://", "https://")):
        candidate = "https://" + candidate
    try:
        netloc = urlparse(candidate).netloc.lower()
    except ValueError:
        return None
    netloc = netloc.split("@")[-1].split(":")[0].strip(".")
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def extract_place_identity(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    match = _PLACE_RE.search(url)
    if match:
        return f"maps:{match.group(1).lower()}"
    match = _CID_RE.search(url)
    if match:
        return f"cid:{match.group(1).lower()}"
    return None


def business_dedupe_key(raw: dict[str, Any]) -> str:
    identity = extract_place_identity(raw.get("url") or raw.get("source_url"))
    if identity:
        return identity
    domain = normalize_domain(raw.get("website"))
    if domain and not domain.endswith("google.com"):
        return f"domain:{domain}"
    name = _slug(str(raw.get("title") or raw.get("name") or ""))
    phone = re.sub(r"\D", "", str(raw.get("phone") or ""))
    address = _slug(str(raw.get("address") or ""))
    basis = "|".join(part for part in (name, phone, address) if part)
    if not basis:
        basis = json.dumps(raw, sort_keys=True, default=str)
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]
    return f"record:{digest}"


def parse_location(raw: dict[str, Any]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    city = clean_text(raw.get("city"))
    state = clean_text(raw.get("state"))
    country = clean_text(raw.get("country"))
    address = clean_text(raw.get("address")) or ""

    if not (city and state):
        match = _CITY_STATE_RE.search(address)
        if match:
            city = city or clean_text(match.group(1))
            state = state or match.group(2)
        else:
            match = _STATE_RE.search(address)
            if match and not state:
                state = match.group(1)
    return city, (state.upper() if state else None), country


def normalize_lead(
    raw: dict[str, Any],
    source: str,
    source_query: Optional[str] = None,
    discovered_at: Optional[str] = None,
) -> dict[str, Any]:
    name = clean_text(raw.get("title") or raw.get("name"))
    if not name:
        raise ValueError("lead is missing a business name")
    city, state, country = parse_location(raw)
    website = clean_text(raw.get("website"))
    if website and not website.startswith(("http://", "https://")):
        website = "https://" + website
    flags: list[str] = []
    if not website:
        flags.append("missing_website")
    if not raw.get("phone"):
        flags.append("missing_phone")
    if not (raw.get("email") or raw.get("all_emails")):
        flags.append("missing_email")
    if not raw.get("category"):
        flags.append("missing_category")
    if not (city and state):
        flags.append("incomplete_location")

    return {
        "name": name,
        "category": clean_text(raw.get("category")),
        "rating": _coerce_float(raw.get("rating")),
        "reviews_count": _coerce_int(raw.get("reviews_count")),
        "phone": normalize_phone(raw.get("phone")) or clean_text(raw.get("phone")),
        "website": website,
        "address": clean_text(raw.get("address")),
        "city": city,
        "state": state,
        "country": country,
        "employee_count": _coerce_int(raw.get("employee_count")),
        "source": source,
        "source_url": clean_text(raw.get("url") or raw.get("source_url")),
        "source_query": source_query,
        "discovered_at": discovered_at or utcnow(),
        "raw_json": json.dumps(raw, sort_keys=True, default=str),
        "dedupe_key": business_dedupe_key(raw),
        "flags_json": json.dumps(sorted(set(flags))),
    }


def _coerce_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(str(value))
    except (TypeError, ValueError):
        return None


def ingest_lead(
    db: Database,
    raw: dict[str, Any],
    source: str,
    source_query: Optional[str] = None,
    actor: str = "import",
) -> tuple[int, bool]:
    """Insert or merge a lead. Returns (lead_id, created)."""
    normalized = normalize_lead(raw, source=source, source_query=source_query)
    existing = db.fetchone(
        "SELECT id, raw_json FROM leads WHERE dedupe_key = ?", (normalized["dedupe_key"],)
    )
    now = utcnow()
    if existing:
        lead_id = int(existing["id"])
        merge_fields = ["category", "rating", "reviews_count", "phone", "website", "address", "city", "state", "country", "employee_count"]
        current = db.fetchone("SELECT * FROM leads WHERE id = ?", (lead_id,))
        updates = {f: normalized[f] for f in merge_fields if normalized.get(f) is not None and not current[f]}
        if updates:
            assignments = ", ".join(f"{field} = ?" for field in updates)
            db.execute(
                f"UPDATE leads SET {assignments}, updated_at = ? WHERE id = ?",
                (*updates.values(), now, lead_id),
            )
            db.audit(actor, "lead.merged", "lead", lead_id, {"fields": list(updates)})
        return lead_id, False

    lead_id = db.insert(
        """INSERT INTO leads(
               dedupe_key, name, category, rating, reviews_count, phone, website,
               address, city, state, country, employee_count, source, source_url,
               source_query, discovered_at, raw_json, normalized_at, flags_json,
               created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            normalized["dedupe_key"], normalized["name"], normalized["category"],
            normalized["rating"], normalized["reviews_count"], normalized["phone"],
            normalized["website"], normalized["address"], normalized["city"],
            normalized["state"], normalized["country"], normalized["employee_count"],
            normalized["source"], normalized["source_url"], normalized["source_query"],
            normalized["discovered_at"], normalized["raw_json"], now,
            normalized["flags_json"], now, now,
        ),
    )
    db.audit(actor, "lead.created", "lead", lead_id, {"source": source})
    return lead_id, True


def ingest_contact(
    db: Database,
    lead_id: int,
    email: str,
    source: str,
    discovery_method: str,
    source_url: Optional[str] = None,
    raw: Optional[dict[str, Any]] = None,
    actor: str = "import",
) -> tuple[int, bool]:
    normalized_email = normalize_email(email)
    if not is_valid_email_syntax(normalized_email):
        raise ValueError(f"invalid email: {email!r}")
    existing = db.fetchone(
        "SELECT id FROM contacts WHERE lead_id = ? AND normalized_email = ?",
        (lead_id, normalized_email),
    )
    now = utcnow()
    if existing:
        db.execute(
            """UPDATE contacts SET source = COALESCE(source, ?), source_url = COALESCE(source_url, ?),
                   updated_at = ? WHERE id = ?""",
            (source, source_url, now, existing["id"]),
        )
        return int(existing["id"]), False
    primary = db.fetchone("SELECT COUNT(*) AS c FROM contacts WHERE lead_id = ?", (lead_id,))
    is_primary = 1 if not primary or int(primary["c"]) == 0 else 0
    contact_id = db.insert(
        """INSERT INTO contacts(
               lead_id, email, normalized_email, source, source_url, discovery_method,
               verification_status, is_primary, raw_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'unverified', ?, ?, ?, ?)""",
        (
            lead_id, email.strip(), normalized_email, source, source_url,
            discovery_method, is_primary,
            json.dumps(raw, sort_keys=True, default=str) if raw else None, now, now,
        ),
    )
    db.audit(actor, "contact.created", "contact", contact_id, {"discovery_method": discovery_method})
    return contact_id, True


def lead_contacts(raw: dict[str, Any]) -> list[tuple[str, str]]:
    """Return explicit (email, discovery_method) pairs found in a raw lead.

    Only explicit, published addresses are accepted. No address is guessed or
    generated from a person's name.
    """
    found: list[tuple[str, str]] = []
    if raw.get("email"):
        found.append((str(raw["email"]), "lead_email_field"))
    for email in raw.get("all_emails") or []:
        found.append((str(email), "website_crawl"))
    for email in raw.get("emails") or []:
        found.append((str(email), "structured_data"))
    deduped: dict[str, tuple[str, str]] = {}
    for email, method in found:
        normalized = normalize_email(email)
        if is_valid_email_syntax(normalized) and normalized not in deduped:
            deduped[normalized] = (normalized, method)
    return list(deduped.values())
