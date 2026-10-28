"""Pre-send compliance and delivery policy gate.

A send is permitted only when every check is explicitly true. Missing,
unparseable, or conflicting information blocks the message.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .config import ReachyConfig
from .models import PolicyDecision
from .normalize import normalize_email
from .suppression import is_suppressed
from .verify import VerificationPolicy, EXPLICIT_DISCOVERY_METHODS

DEFAULT_ALLOWED_JURISDICTIONS = {"US"}


@dataclass
class PolicyEngine:
    config: ReachyConfig
    allowed_jurisdictions: set[str] = field(default_factory=lambda: set(DEFAULT_ALLOWED_JURISDICTIONS))

    def check_send(self, db, message: dict[str, Any]) -> PolicyDecision:
        checks: dict[str, bool] = {}
        reasons: list[str] = []
        snapshot: dict[str, Any] = {}

        campaign = _row(db, "campaigns", message["campaign_id"])
        account = _row(db, "accounts", message["account_id"]) if message.get("account_id") else None
        contact = _row(db, "contacts", message["contact_id"])
        lead = _row(db, "leads", message["lead_id"])

        campaign_policy = _json(campaign.get("policy_json") if campaign else None)
        dry_run = bool(campaign and campaign.get("dry_run"))
        test_mode = bool(campaign and campaign.get("test_mode"))

        def add(name: str, ok: bool, reason: str) -> None:
            checks[name] = bool(ok)
            if not ok:
                reasons.append(reason)

        global_pause = db.get_setting("global_pause", "0") == "1"
        add("global_not_paused", not global_pause, "Global pause is active")
        add(
            "campaign_running",
            bool(campaign and campaign["status"] == "RUNNING"),
            f"Campaign is not running ({campaign['status'] if campaign else 'missing'})",
        )
        add(
            "campaign_approved",
            bool(campaign and campaign.get("approved_at") and campaign.get("approved_by")),
            "Campaign has no recorded approval",
        )

        listing = _row(db, "lists", campaign["list_id"]) if campaign else None
        approval = db.fetchone("SELECT * FROM list_approvals WHERE list_id = ?", (campaign["list_id"],)) if campaign else None
        add(
            "list_approved",
            bool(listing and listing["status"] == "APPROVED" and approval),
            "Lead list is not approved through sample review",
        )

        add("contact_present", bool(contact), "Contact record is missing")
        if contact:
            verification_status = contact["verification_status"]
            allow_catch_all = bool(campaign_policy.get("allow_catch_all", self.config.allow_catch_all))
            sendable = verification_status == "valid" or (
                verification_status == "catch_all" and allow_catch_all
            )
            add(
                "contact_verified",
                sendable,
                f"Contact verification state is '{verification_status}'",
            )
            add(
                "contact_explicit_source",
                bool(contact["source"]) and contact["discovery_method"] in EXPLICIT_DISCOVERY_METHODS,
                "Contact was not sourced from an explicit published location",
            )
            suppression = is_suppressed(db, contact["email"])
            add("not_suppressed", suppression is None, "Contact is on the global suppression list")
            snapshot["contact"] = {
                "email": contact["email"],
                "source": contact["source"],
                "discovery_method": contact["discovery_method"],
                "verification_status": verification_status,
                "suppressed": suppression is not None,
            }

        jurisdiction = str(campaign_policy.get("jurisdiction") or "").upper().strip()
        lawful_basis = str(campaign_policy.get("lawful_basis") or "").strip()
        reviewed = bool(campaign_policy.get("policy_reviewed"))
        add("jurisdiction_declared", bool(jurisdiction), "Campaign jurisdiction is not declared")
        add(
            "jurisdiction_supported",
            bool(jurisdiction) and jurisdiction in self.allowed_jurisdictions,
            f"Jurisdiction '{jurisdiction}' is not in the configured allow-list",
        )
        add("lawful_basis_recorded", bool(lawful_basis), "Lawful basis / campaign policy is not recorded")
        add("policy_reviewed", reviewed, "Campaign policy has not been reviewed and attested")
        recipient_country = str((lead or {}).get("country") or "").upper().strip()
        add(
            "recipient_jurisdiction_consistent",
            (not recipient_country) or (not jurisdiction) or recipient_country == jurisdiction,
            f"Recipient country '{recipient_country}' conflicts with campaign jurisdiction '{jurisdiction}'",
        )

        if dry_run:
            add("account_authorized", True, "")
            add("provider_permitted_use", True, "")
            add("under_daily_limit", True, "")
        else:
            add("account_present", account is not None, "Sending account is missing")
            add(
                "account_authorized",
                bool(account and account["status"] == "ACTIVE" and account.get("authorized_at") and not account.get("revoked_at")),
                "Sending account is not authorized/active",
            )
            account_config = _json(account["config_json"]) if account else {}
            add(
                "provider_permitted_use",
                bool(account_config.get("permitted_use_acknowledged_at")),
                "Provider permitted-use acknowledgement is missing for this account",
            )
            limit = int(account["daily_limit"]) if account else 0
            today = datetime.now(timezone.utc).date().isoformat()
            used = int(account["sends_today"]) if account and account.get("sends_today_date") == today else 0
            add(
                "under_daily_limit",
                bool(account and used < limit),
                f"Daily sending limit reached ({used}/{limit})",
            )
            add(
                "sender_identity_matches_account",
                bool(account and message.get("from_email") == account["email"]),
                "From address does not match the authorized account",
            )

        if test_mode and not dry_run:
            add(
                "test_recipient_valid",
                bool(self.config.test_recipient and normalize_email(self.config.test_recipient)),
                "Test mode requires REACHY_TEST_RECIPIENT; the worker redirects all mail to it",
            )

        sender_identity = str((campaign or {}).get("sender_identity") or "").strip()
        add("sender_identity_declared", bool(sender_identity), "Campaign sender identity is not declared")

        snapshot.update(
            {
                "campaign_id": message["campaign_id"],
                "message_id": message.get("id"),
                "to_email": message.get("to_email"),
                "from_email": message.get("from_email"),
                "dry_run": dry_run,
                "test_mode": test_mode,
                "jurisdiction": jurisdiction,
                "lawful_basis": lawful_basis,
            }
        )
        return PolicyDecision(allowed=all(checks.values()), checks=checks, reasons=reasons, snapshot=snapshot)


def _row(db, table: str, row_id: Optional[int]) -> Optional[dict[str, Any]]:
    if row_id is None:
        return None
    row = db.fetchone(f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    return dict(row) if row else None


def _json(value: Optional[str]) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}
