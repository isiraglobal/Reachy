"""Reply synchronization, classification, follow-up cancellation, and drafts."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from .campaign import cancel_followups
from .db import Database, utcnow
from .models import InboundMessage
from .normalize import normalize_email
from .providers.base import EmailProvider
from .suppression import add_suppression

COMPLAINT_TERMS = [
    "abuse",
    "spam",
    "complaint",
    "report you",
    "legal action",
    "harass",
    "gdpr",
    "cease and desist",
]
UNSUBSCRIBE_TERMS = [
    "unsubscribe",
    "remove me",
    "opt out",
    "opt-out",
    "take me off",
    "stop emailing",
    "do not contact",
    "don't contact",
]
INTERESTED_TERMS = [
    "interested",
    "let's chat",
    "lets chat",
    "call me",
    "available",
    "schedule",
    "book a",
    "tell me more",
    "send more",
    "sounds good",
    "works for me",
]
NOT_INTERESTED_TERMS = ["not interested", "no thanks", "no thank you", "not for us"]
REFERRAL_TERMS = ["forwarded", "reach out to", "contact my colleague", "cc'ing", "you should talk to"]
OOO_TERMS = ["out of office", "out of the office", "on vacation", "away from", "annual leave"]
AUTOMATED_TERMS = ["automatic reply", "auto-reply", "autoreply", "delivery status", "mail delivery failed"]


def classify_reply(message: InboundMessage) -> tuple[str, str]:
    """Return (classification, source).

    Unsubscribe and complaint detection takes precedence over every other
    classification and over any model output.
    """
    text = f"{message.subject}\n{message.body}".lower()
    headers = {k.lower(): v for k, v in message.headers.items()}
    from_addr = message.from_email.lower()

    if any(term in text for term in COMPLAINT_TERMS):
        return "complaint", "rule:complaint"
    if any(term in text for term in UNSUBSCRIBE_TERMS):
        return "unsubscribe", "rule:unsubscribe"

    auto_submitted = headers.get("auto-submitted", "").lower()
    precedence = headers.get("precedence", "").lower()
    if auto_submitted and auto_submitted != "no":
        if any(term in text for term in OOO_TERMS):
            return "out_of_office", "header:auto-submitted"
        return "automated", "header:auto-submitted"
    if precedence in {"bulk", "junk", "auto_reply"}:
        return "automated", "header:precedence"
    if any(term in text for term in OOO_TERMS):
        return "out_of_office", "rule:out_of_office"
    if any(term in text for term in AUTOMATED_TERMS) or from_addr.startswith(("no-reply", "noreply", "mailer-daemon")):
        return "automated", "rule:automated"

    if any(term in text for term in REFERRAL_TERMS):
        return "referral", "rule:referral"
    if any(term in text for term in INTERESTED_TERMS):
        return "interested", "rule:interested"
    if any(term in text for term in NOT_INTERESTED_TERMS):
        return "not_interested", "rule:not_interested"
    return "uncertain", "rule:uncertain"


def _associate(db: Database, inbound: InboundMessage) -> Optional[dict[str, Any]]:
    candidates = [inbound.in_reply_to, *inbound.references, inbound.message_id_header]
    for header in [c for c in candidates if c]:
        row = db.fetchone("SELECT * FROM messages WHERE message_id_header = ?", (header,))
        if row:
            return dict(row)
    contact = db.fetchone(
        "SELECT * FROM contacts WHERE normalized_email = ? ORDER BY id DESC LIMIT 1",
        (normalize_email(inbound.from_email),),
    )
    if not contact:
        return None
    message = db.fetchone(
        "SELECT * FROM messages WHERE contact_id = ? ORDER BY id DESC LIMIT 1",
        (contact["id"],),
    )
    return dict(message) if message else None


def ingest_reply(
    db: Database,
    account_id: int,
    inbound: InboundMessage,
    actor: str = "replier",
    stop_on_automated: bool = False,
) -> dict[str, Any]:
    existing = db.fetchone(
        "SELECT id FROM replies WHERE account_id=? AND provider_reply_id=?",
        (account_id, inbound.provider_id),
    )
    if existing:
        return {"status": "duplicate", "reply_id": int(existing["id"])}
    if inbound.message_id_header:
        duplicate = db.fetchone(
            "SELECT id FROM replies WHERE account_id=? AND message_id_header=?",
            (account_id, inbound.message_id_header),
        )
        if duplicate:
            return {"status": "duplicate", "reply_id": int(duplicate["id"])}

    classification, source = classify_reply(inbound)
    associated = _associate(db, inbound)
    contact_id = associated["contact_id"] if associated else None
    campaign_id = associated["campaign_id"] if associated else None
    lead_id = associated["lead_id"] if associated else None
    if not contact_id:
        contact = db.fetchone(
            "SELECT * FROM contacts WHERE normalized_email = ? ORDER BY id DESC LIMIT 1",
            (normalize_email(inbound.from_email),),
        )
        if contact:
            contact_id = contact["id"]
            lead_id = contact["lead_id"]
    now = utcnow()
    reply_id = db.insert(
        """INSERT INTO replies(
               account_id, campaign_id, lead_id, contact_id, provider_reply_id,
               message_id_header, in_reply_to, from_email, subject, body, received_at,
               classification, classification_source, stop_followups, raw_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            account_id, campaign_id, lead_id, contact_id, inbound.provider_id,
            inbound.message_id_header, inbound.in_reply_to, inbound.from_email,
            inbound.subject, inbound.body, inbound.received_at, classification,
            source, 0, json.dumps(inbound.raw or {}, sort_keys=True), now,
        ),
    )

    stop = classification in {"interested", "not_interested", "referral", "unsubscribe", "complaint", "uncertain"}
    if classification in {"automated", "out_of_office"}:
        stop = stop_on_automated
    if stop and contact_id:
        db.execute("UPDATE replies SET stop_followups=1 WHERE id=?", (reply_id,))
        cancel_followups(db, int(contact_id), campaign_id=campaign_id, reason=classification, actor=actor)

    if classification == "unsubscribe":
        add_suppression(
            db, inbound.from_email, "unsubscribe", source="reply", campaign_id=campaign_id,
            notes=f"reply {reply_id}", actor=actor,
        )
        _event(db, associated, "UNSUBSCRIBE", {"reply_id": reply_id})
    elif classification == "complaint":
        add_suppression(
            db, inbound.from_email, "complaint", source="reply", campaign_id=campaign_id,
            notes=f"reply {reply_id}", actor=actor,
        )
        _event(db, associated, "COMPLAINT", {"reply_id": reply_id})
    elif classification == "interested" and contact_id:
        db.insert(
            """INSERT INTO reply_drafts(reply_id, body, status, created_at)
               VALUES (?, ?, 'PENDING_APPROVAL', ?)""",
            (
                reply_id,
                "Draft: thank the sender, confirm the requested next step, and ask one "
                "clarifying question. Edit before approving. Reachy never sends this "
                "automatically.",
                now,
            ),
        )

    db.audit(actor, "reply.ingested", "reply", reply_id, {"classification": classification, "stop": stop})
    return {
        "status": "stored",
        "reply_id": reply_id,
        "classification": classification,
        "classification_source": source,
        "stop_followups": stop,
        "campaign_id": campaign_id,
    }


def _event(db: Database, associated: Optional[dict[str, Any]], event_type: str, detail: dict[str, Any]) -> None:
    if not associated:
        return
    db.execute(
        "INSERT INTO message_events(message_id, event_type, detail_json, created_at) VALUES (?, ?, ?, ?)",
        (associated["id"], event_type, json.dumps(detail, sort_keys=True), utcnow()),
    )


def sync_replies(
    db: Database,
    account_id: int,
    provider: EmailProvider,
    since: Optional[datetime] = None,
    actor: str = "reply_sync",
    stop_on_automated: bool = False,
) -> dict[str, Any]:
    inbound = provider.fetch_replies(since=since)
    stored = 0
    duplicates = 0
    by_class: dict[str, int] = {}
    for message in inbound:
        outcome = ingest_reply(db, account_id, message, actor=actor, stop_on_automated=stop_on_automated)
        if outcome["status"] == "duplicate":
            duplicates += 1
        else:
            stored += 1
            by_class[outcome["classification"]] = by_class.get(outcome["classification"], 0) + 1
    db.execute("UPDATE accounts SET last_sync_at=?, updated_at=? WHERE id=?", (utcnow(), utcnow(), account_id))
    db.audit(actor, "replies.synced", "account", account_id, {"stored": stored, "duplicates": duplicates})
    return {"stored": stored, "duplicates": duplicates, "classifications": by_class}


def record_bounce(
    db: Database,
    account_id: int,
    email: str,
    kind: str = "hard",
    actor: str = "bounce_processor",
) -> dict[str, Any]:
    kind = kind.lower()
    if kind not in {"hard", "soft"}:
        raise ValueError("bounce kind must be 'hard' or 'soft'")
    contact = db.fetchone(
        "SELECT * FROM contacts WHERE normalized_email = ? ORDER BY id DESC LIMIT 1",
        (normalize_email(email),),
    )
    message = None
    if contact:
        message = db.fetchone(
            "SELECT * FROM messages WHERE contact_id=? ORDER BY id DESC LIMIT 1", (contact["id"],)
        )
    if kind == "hard":
        add_suppression(db, email, "hard_bounce", source="bounce", actor=actor)
        if contact:
            cancel_followups(
                db, int(contact["id"]), campaign_id=int(message["campaign_id"]) if message else None,
                reason="hard_bounce", actor=actor,
            )
    if message:
        db.execute(
            "INSERT INTO message_events(message_id, event_type, detail_json, created_at) VALUES (?, ?, ?, ?)",
            (message["id"], "HARD_BOUNCE" if kind == "hard" else "SOFT_BOUNCE",
             json.dumps({"email": email}, sort_keys=True), utcnow()),
        )
    db.audit(actor, f"bounce.{kind}", "account", account_id, {"email": email})
    return {"status": "suppressed" if kind == "hard" else "recorded", "kind": kind, "email": email}


def approve_reply_draft(db: Database, draft_id: int, approved_by: str) -> dict[str, Any]:
    """Approve an external reply draft for manual sending.

    Approval does not submit the message; outbound replies remain under human
    control until a dedicated reply-send workflow is explicitly enabled.
    """
    row = db.fetchone("SELECT * FROM reply_drafts WHERE id = ?", (draft_id,))
    if not row:
        raise KeyError(f"reply draft {draft_id} not found")
    if row["status"] != "PENDING_APPROVAL":
        raise ValueError(f"draft is {row['status']}, not PENDING_APPROVAL")
    db.execute(
        "UPDATE reply_drafts SET status='APPROVED', approved_at=?, approved_by=? WHERE id=?",
        (utcnow(), approved_by, draft_id),
    )
    db.audit(approved_by, "reply_draft.approved", "reply_draft", draft_id)
    return {"draft_id": draft_id, "status": "APPROVED"}


def reject_reply_draft(db: Database, draft_id: int, rejected_by: str) -> dict[str, Any]:
    db.execute("UPDATE reply_drafts SET status='REJECTED' WHERE id=?", (draft_id,))
    db.audit(rejected_by, "reply_draft.rejected", "reply_draft", draft_id)
    return {"draft_id": draft_id, "status": "REJECTED"}


def list_reply_drafts(db: Database, status: str = "PENDING_APPROVAL") -> list[dict[str, Any]]:
    rows = db.fetchall(
        "SELECT * FROM reply_drafts WHERE status = ? ORDER BY created_at DESC", (status,)
    )
    return [dict(row) for row in rows]
