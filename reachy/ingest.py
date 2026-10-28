"""Import existing datasets and browser-discovered leads into Reachy."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Optional

from .db import Database, utcnow
from .normalize import ingest_contact, ingest_lead, lead_contacts
from .scoring import ICPProfile, score_and_store
from .verify import DNSBackend, VerificationPolicy, verify_contact


def load_records(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path).expanduser()
    if not source.exists():
        raise FileNotFoundError(source)
    if source.suffix.lower() == ".json":
        data = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for key in ("leads", "records", "data", "items"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        if not isinstance(data, list):
            raise ValueError("JSON must be a list or contain a list under 'leads'")
        return [dict(item) for item in data]
    if source.suffix.lower() == ".csv":
        with source.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    raise ValueError("supported import formats: .json, .csv")


def ensure_list(db: Database, name: str, icp_profile_id: Optional[int] = None) -> int:
    row = db.fetchone("SELECT id FROM lists WHERE name = ?", (name,))
    if row:
        return int(row["id"])
    now = utcnow()
    list_id = db.insert(
        "INSERT INTO lists(name, icp_profile_id, status, created_at, updated_at) VALUES (?, ?, 'DRAFT', ?, ?)",
        (name, icp_profile_id, now, now),
    )
    db.audit("user", "list.created", "list", list_id, {"name": name})
    return list_id


def import_records(
    db: Database,
    records: list[dict[str, Any]],
    source: str,
    list_name: str,
    source_query: Optional[str] = None,
    icp: Optional[ICPProfile] = None,
    icp_profile_id: Optional[int] = None,
    verify: bool = True,
    dns_backend: Optional[DNSBackend] = None,
    verification_policy: Optional[VerificationPolicy] = None,
    actor: str = "import",
) -> dict[str, Any]:
    list_id = ensure_list(db, list_name, icp_profile_id)
    stats = {
        "records": len(records),
        "created": 0,
        "merged": 0,
        "contacts": 0,
        "duplicate_contacts": 0,
        "verification": {},
        "errors": [],
    }
    for raw in records:
        try:
            lead_id, created = ingest_lead(db, raw, source=source, source_query=source_query, actor=actor)
        except Exception as exc:  # noqa: BLE001
            stats["errors"].append({"record": raw.get("title") or raw.get("name"), "error": str(exc)})
            continue
        stats["created" if created else "merged"] += 1
        db.execute(
            "INSERT OR IGNORE INTO list_leads(list_id, lead_id, added_at) VALUES (?, ?, ?)",
            (list_id, lead_id, utcnow()),
        )
        if icp:
            score_and_store(db, lead_id, icp, actor=actor)
        for email, method in lead_contacts(raw):
            try:
                contact_id, new = ingest_contact(
                    db,
                    lead_id,
                    email,
                    source=source,
                    discovery_method=method,
                    source_url=raw.get("url") or raw.get("source_url"),
                    raw=raw,
                    actor=actor,
                )
            except ValueError as exc:
                stats["errors"].append({"record": raw.get("title"), "email": email, "error": str(exc)})
                continue
            if not new:
                stats["duplicate_contacts"] += 1
                continue
            stats["contacts"] += 1
            if verify:
                result = verify_contact(
                    db, contact_id, backend=dns_backend, policy=verification_policy, actor=actor
                )
                stats["verification"][result.status] = stats["verification"].get(result.status, 0) + 1
    db.audit(actor, "import.completed", "list", list_id, {"source": source, "records": len(records)})
    stats["list_id"] = list_id
    stats["list_name"] = list_name
    return stats


def import_file(
    db: Database,
    path: str | Path,
    source: str,
    list_name: str,
    **kwargs: Any,
) -> dict[str, Any]:
    records = load_records(path)
    return import_records(db, records, source=source, list_name=list_name, **kwargs)


def discover_leads(
    query: str,
    limit: int = 10,
    headed: bool = True,
    backend: str = "auto",
    enrich: bool = True,
) -> list[dict[str, Any]]:
    """Browser-assisted Google Maps discovery using the retained pipeline."""
    from google_maps_leads.scraper import GoogleMapsScraper

    scraper = GoogleMapsScraper(headed=headed, backend=backend)
    try:
        leads = scraper.scrape_leads(query=query, limit=limit, enrich=enrich)
        return [lead.to_dict() for lead in leads]
    finally:
        scraper.close()
