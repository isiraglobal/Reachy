"""Lead/contact normalization, provenance, and deduplication."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
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


def _normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        parts = [str(part).strip() for part in value]
    else:
        parts = [str(value).strip()]
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part and part not in seen:
            seen.add(part)
            result.append(part)
    return result


def normalize_lead(
    raw: dict[str, Any],
    source: str,
    source_query: Optional[str] = None,
    discovered_at: Optional[str] = None,
    *,
    tags: Any = None,
    run: Any = None,
    run_id: Any = None,
    run_name: Any = None,
    task: Any = None,
    task_id: Any = None,
    task_name: Any = None,
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

    run_value = run_id if run_id is not None else (run if run is not None else run_name)
    run_name_value = run_name if run_name is not None else run_value
    run_field_value = run if run is not None else run_value
    task_value = task_id if task_id is not None else (task if task is not None else task_name)
    task_name_value = task_name if task_name is not None else task_value
    task_field_value = task if task is not None else task_value

    tag_values = _normalize_tags(tags)
    for value in (run_value, task_value):
        if value is not None:
            text = str(value).strip()
            if text and text not in tag_values:
                tag_values.append(text)

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
        "run_id": run_value,
        "run": run_field_value,
        "run_name": run_name_value,
        "task_id": task_value,
        "task": task_field_value,
        "task_name": task_name_value,
        "tags": json.dumps(tag_values),
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
    discovered_at: Optional[str] = None,
    actor: str = "import",
    *,
    tags: Any = None,
    run: Any = None,
    run_id: Any = None,
    run_name: Any = None,
    task: Any = None,
    task_id: Any = None,
    task_name: Any = None,
    **kwargs: Any,
) -> tuple[int, bool]:
    """Insert or merge a lead. Returns (lead_id, created).

    Deduplication is hard-wired by ``dedupe_key``: a matching business is
    never inserted twice. Run/task/tag provenance is merged onto the existing
    record instead.
    """
    normalized = normalize_lead(
        raw,
        source=source,
        source_query=source_query,
        discovered_at=discovered_at,
        tags=tags,
        run=run,
        run_id=run_id,
        run_name=run_name,
        task=task,
        task_id=task_id,
        task_name=task_name,
    )
    existing = db.fetchone(
        "SELECT id, raw_json FROM leads WHERE dedupe_key = ?", (normalized["dedupe_key"],)
    )
    now = utcnow()
    alias_fields = ["run_id", "run", "run_name", "task_id", "task", "task_name"]
    if existing:
        lead_id = int(existing["id"])
        merge_fields = ["category", "rating", "reviews_count", "phone", "website", "address", "city", "state", "country", "employee_count"]
        current = db.fetchone("SELECT * FROM leads WHERE id = ?", (lead_id,))
        updates = {f: normalized[f] for f in merge_fields if normalized.get(f) is not None and not current[f]}
        try:
            current_tags = json.loads(current["tags"] or "[]")
        except (TypeError, ValueError):
            current_tags = []
        new_tags = json.loads(normalized["tags"] or "[]")
        merged_tags = list(current_tags)
        for tag in new_tags:
            if tag not in merged_tags:
                merged_tags.append(tag)
        if merged_tags != current_tags:
            updates["tags"] = json.dumps(merged_tags)
        for field in alias_fields:
            if normalized.get(field) is not None and not current[field]:
                updates[field] = normalized[field]
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
               run_id, run, run_name, task_id, task, task_name, tags,
               created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            normalized["dedupe_key"], normalized["name"], normalized["category"],
            normalized["rating"], normalized["reviews_count"], normalized["phone"],
            normalized["website"], normalized["address"], normalized["city"],
            normalized["state"], normalized["country"], normalized["employee_count"],
            normalized["source"], normalized["source_url"], normalized["source_query"],
            normalized["discovered_at"], normalized["raw_json"], now,
            normalized["flags_json"],
            normalized["run_id"], normalized["run"], normalized["run_name"],
            normalized["task_id"], normalized["task"], normalized["task_name"],
            normalized["tags"], now, now,
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


def _rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def query_leads(
    db: Database,
    *,
    tag: Any = None,
    tags: Any = None,
    task: Any = None,
    task_id: Any = None,
    task_name: Any = None,
    run: Any = None,
    run_id: Any = None,
    run_name: Any = None,
    list_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Query leads from the single database with run/task/tag separation."""
    tag_values: list[str] = []
    if tag is not None:
        tag_values.append(str(tag))
    if tags is not None:
        if isinstance(tags, str):
            tag_values.extend(part.strip() for part in tags.split(",") if part.strip())
        elif isinstance(tags, (list, tuple, set)):
            tag_values.extend(str(part).strip() for part in tags if str(part).strip())
        else:
            tag_values.append(str(tags).strip())

    task_values = [str(v) for v in (task, task_id, task_name, kwargs.get("task")) if v is not None]
    run_values = [str(v) for v in (run, run_id, run_name, kwargs.get("run")) if v is not None]

    conditions: list[str] = []
    params: list[Any] = []

    if tag_values:
        tag_conditions = []
        for value in tag_values:
            tag_conditions.append("l.tags LIKE ?")
            params.append(f'%"{value}"%')
        # Fall back to substring match for tags stored without JSON quoting.
        for value in tag_values:
            tag_conditions.append("l.tags LIKE ?")
            params.append(f"%{value}%")
        conditions.append("(" + " OR ".join(tag_conditions) + ")")

    if task_values:
        task_conditions = []
        for value in task_values:
            task_conditions.append("l.task = ?")
            params.append(value)
            task_conditions.append("l.task_id = ?")
            params.append(value)
            task_conditions.append("l.task_name = ?")
            params.append(value)
            task_conditions.append("l.tags LIKE ?")
            params.append(f"%{value}%")
        conditions.append("(" + " OR ".join(task_conditions) + ")")

    if run_values:
        run_conditions = []
        for value in run_values:
            run_conditions.append("l.run = ?")
            params.append(value)
            run_conditions.append("l.run_id = ?")
            params.append(value)
            run_conditions.append("l.run_name = ?")
            params.append(value)
            run_conditions.append("l.tags LIKE ?")
            params.append(f"%{value}%")
        conditions.append("(" + " OR ".join(run_conditions) + ")")

    if list_name is not None:
        conditions.append("ll.list_id = (SELECT id FROM lists WHERE name = ?)")
        params.append(list_name)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    join = "JOIN list_leads ll ON ll.lead_id = l.id" if list_name is not None else "LEFT JOIN list_leads ll ON ll.lead_id = l.id"
    sql = f"""
        SELECT DISTINCT l.*, c.email, c.verification_status
        FROM leads l
        {join}
        LEFT JOIN contacts c ON c.lead_id = l.id AND c.is_primary = 1
        {where}
        ORDER BY l.id DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    rows = db.fetchall(sql, params)
    return [dict(row) for row in rows]


def get_leads(db: Database, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return query_leads(db, *args, **kwargs)


def list_leads(db: Database, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return query_leads(db, *args, **kwargs)


def search_leads(db: Database, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return query_leads(db, *args, **kwargs)


def leads_by_tag(db: Database, tag: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return query_leads(db, tag=tag, **kwargs)


def leads_for_task(db: Database, task: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return query_leads(db, task=task, **kwargs)


def leads_for_run(db: Database, run: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return query_leads(db, run=run, **kwargs)


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
