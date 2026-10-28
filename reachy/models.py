"""Typed values shared across discovery, verification, and delivery."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


VERIFICATION_STATUSES = {"valid", "invalid", "catch_all", "unknown", "unverified"}

REPLY_CLASSIFICATIONS = {
    "interested",
    "not_interested",
    "referral",
    "out_of_office",
    "automated",
    "unsubscribe",
    "complaint",
    "uncertain",
}


@dataclass
class NormalizedLead:
    name: str
    dedupe_key: str
    source: str
    raw: dict[str, Any]
    discovered_at: str
    category: Optional[str] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    employee_count: Optional[int] = None
    source_url: Optional[str] = None
    source_query: Optional[str] = None
    flags: list[str] = field(default_factory=list)


@dataclass
class VerificationResult:
    status: str
    method: str
    detail: str = ""
    checked_at: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in VERIFICATION_STATUSES:
            raise ValueError(f"invalid verification status: {self.status}")


@dataclass
class ScoreResult:
    score: int
    reason: str
    evidence: list[str]
    flags: list[str]
    qualified: bool


@dataclass
class OutboundMessage:
    from_email: str
    from_name: str
    to_email: str
    subject: str
    body: str
    message_id_header: str
    reply_to: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)
    campaign_id: Optional[int] = None
    contact_id: Optional[int] = None
    message_row_id: Optional[int] = None


@dataclass
class SendResult:
    status: str  # accepted | failed | uncertain
    provider_message_id: Optional[str] = None
    error: Optional[str] = None
    retryable: bool = False

    def __post_init__(self) -> None:
        if self.status not in {"accepted", "failed", "uncertain"}:
            raise ValueError(f"invalid send status: {self.status}")


@dataclass
class InboundMessage:
    provider_id: str
    from_email: str
    subject: str
    body: str
    received_at: str
    message_id_header: Optional[str] = None
    in_reply_to: Optional[str] = None
    references: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyDecision:
    allowed: bool
    checks: dict[str, bool]
    reasons: list[str]
    snapshot: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "checks": self.checks,
            "reasons": self.reasons,
            "snapshot": self.snapshot,
        }


ISO_FORMAT_HINT = "%Y-%m-%dT%H:%M:%S%z"


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
