"""Ideal Customer Profile (ICP) scoring with transparent evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from .db import Database, utcnow
from .models import ScoreResult
from .normalize import FREE_EMAIL_DOMAINS, normalize_domain


@dataclass
class ICPProfile:
    name: str
    industries: list[str] = field(default_factory=list)
    business_types: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    min_rating: Optional[float] = None
    min_reviews: Optional[int] = None
    min_employees: Optional[int] = None
    max_employees: Optional[int] = None
    required_evidence: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    weights: dict[str, int] = field(
        default_factory=lambda: {
            "industry": 30,
            "geography": 20,
            "business_type": 15,
            "size": 15,
            "reputation": 20,
        }
    )
    min_score: int = 60

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "industries": self.industries,
            "business_types": self.business_types,
            "cities": self.cities,
            "states": self.states,
            "countries": self.countries,
            "min_rating": self.min_rating,
            "min_reviews": self.min_reviews,
            "min_employees": self.min_employees,
            "max_employees": self.max_employees,
            "required_evidence": self.required_evidence,
            "exclusions": self.exclusions,
            "weights": self.weights,
            "min_score": self.min_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ICPProfile":
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in allowed})


def score_lead(lead: dict[str, Any], icp: ICPProfile) -> ScoreResult:
    score = 0
    evidence: list[str] = []
    flags: list[str] = []
    checks: dict[str, bool] = {}

    category = (lead.get("category") or "").lower()
    name = (lead.get("name") or lead.get("title") or "").lower()
    city = (lead.get("city") or "").lower()
    state = (lead.get("state") or "").upper()
    country = (lead.get("country") or "").lower()
    website_domain = normalize_domain(lead.get("website"))
    employees = lead.get("employee_count")
    rating = lead.get("rating")
    reviews = lead.get("reviews_count")

    # Exclusions are hard blocks.
    for term in icp.exclusions:
        term_l = term.lower()
        if term_l and (term_l in category or term_l in name):
            return ScoreResult(0, f"Excluded: matched '{term}'", [f"exclusion:{term}"], ["excluded"], False)

    if icp.industries:
        matched = [term for term in icp.industries if term.lower() in category or term.lower() in name]
        checks["industry"] = bool(matched)
        if matched:
            score += icp.weights.get("industry", 30)
            evidence.append(f"industry match: {', '.join(matched)} from category '{lead.get('category')}'")
    else:
        checks["industry"] = True

    if icp.business_types:
        matched = [term for term in icp.business_types if term.lower() in category]
        checks["business_type"] = bool(matched)
        if matched:
            score += icp.weights.get("business_type", 15)
            evidence.append(f"business type match: {', '.join(matched)}")
    else:
        checks["business_type"] = True

    geo_configured = bool(icp.cities or icp.states or icp.countries)
    if geo_configured:
        geo_match = (
            (city and any(city == c.lower() for c in icp.cities))
            or (state and state in {s.upper() for s in icp.states})
            or (country and any(country == c.lower() for c in icp.countries))
        )
        checks["geography"] = bool(geo_match)
        if geo_match:
            score += icp.weights.get("geography", 20)
            evidence.append(f"geography match: {city or 'n/a'}, {state or 'n/a'}, {country or 'n/a'}")
    else:
        checks["geography"] = True

    size_configured = icp.min_employees is not None or icp.max_employees is not None
    if size_configured:
        if employees is None:
            checks["size"] = False
            flags.append("unknown_employee_count")
        else:
            in_range = (
                (icp.min_employees is None or int(employees) >= icp.min_employees)
                and (icp.max_employees is None or int(employees) <= icp.max_employees)
            )
            checks["size"] = in_range
            if in_range:
                score += icp.weights.get("size", 15)
                evidence.append(f"employee count: {employees}")
    else:
        checks["size"] = True

    reputation_configured = icp.min_rating is not None or icp.min_reviews is not None
    if reputation_configured:
        rating_ok = icp.min_rating is None or (rating is not None and float(rating) >= icp.min_rating)
        reviews_ok = icp.min_reviews is None or (reviews is not None and int(reviews) >= icp.min_reviews)
        checks["reputation"] = bool(rating_ok and reviews_ok)
        if checks["reputation"]:
            score += icp.weights.get("reputation", 20)
            evidence.append(f"{reviews} reviews at {rating} stars")
        if rating is None or reviews is None:
            flags.append("missing_reputation_data")
    else:
        checks["reputation"] = True

    for required in icp.required_evidence:
        if lead.get(required) in (None, "", []):
            flags.append(f"missing_required:{required}")
            checks[f"required:{required}"] = False

    if website_domain and website_domain in FREE_EMAIL_DOMAINS:
        flags.append("free_email_domain")

    if not evidence:
        evidence.append("no positive fit evidence found")

    missing = [name_ for name_ in ("category", "city", "state", "website", "phone") if not lead.get(name_)]
    if missing:
        flags.append("missing_fields:" + ",".join(missing))

    qualified = (
        score >= icp.min_score
        and all(checks.values())
        and not any(flag.startswith("missing_required:") for flag in flags)
    )
    reason = (
        f"Score {score}/{sum(icp.weights.values())}; "
        f"criteria met: {', '.join(k for k, v in checks.items() if v) or 'none'}; "
        f"criteria missed: {', '.join(k for k, v in checks.items() if not v) or 'none'}"
    )
    return ScoreResult(score, reason, evidence, sorted(set(flags)), qualified)


def save_icp(db: Database, icp: ICPProfile, actor: str = "user") -> int:
    now = utcnow()
    existing = db.fetchone("SELECT id FROM icp_profiles WHERE name = ?", (icp.name,))
    if existing:
        db.execute(
            "UPDATE icp_profiles SET config_json=?, updated_at=? WHERE id=?",
            (json.dumps(icp.to_dict(), sort_keys=True), now, existing["id"]),
        )
        return int(existing["id"])
    icp_id = db.insert(
        "INSERT INTO icp_profiles(name, config_json, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (icp.name, json.dumps(icp.to_dict(), sort_keys=True), now, now),
    )
    db.audit(actor, "icp.created", "icp", icp_id, {"name": icp.name})
    return icp_id


def load_icp(db: Database, name: str) -> Optional[tuple[int, ICPProfile]]:
    row = db.fetchone("SELECT * FROM icp_profiles WHERE name = ?", (name,))
    if not row:
        return None
    return int(row["id"]), ICPProfile.from_dict(json.loads(row["config_json"]))


def score_and_store(db: Database, lead_id: int, icp: ICPProfile, actor: str = "scorer") -> ScoreResult:
    row = db.fetchone("SELECT * FROM leads WHERE id = ?", (lead_id,))
    if not row:
        raise KeyError(f"lead {lead_id} not found")
    lead = dict(row)
    result = score_lead(lead, icp)
    db.execute(
        """UPDATE leads SET qualification_score=?, qualification_reason=?,
               qualification_evidence=?, flags_json=?, updated_at=? WHERE id=?""",
        (
            result.score,
            result.reason,
            json.dumps(result.evidence),
            json.dumps(result.flags),
            utcnow(),
            lead_id,
        ),
    )
    return result
