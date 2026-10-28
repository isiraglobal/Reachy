"""Open rate tracking, transparent beacon generation, and automated bounce detection.

Built by ISIRA Automations for Reachy.
Provides tamper-proof open tracking tokens, 1x1 beacon pixel rendering,
engagement analytics, and intelligent delivery failure / bounce recognition.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .db import Database, utcnow
from .models import InboundMessage
from .normalize import normalize_email
from .replies import record_bounce

# 1x1 transparent PNG binary bytes (valid image returned to email clients)
TRANSPARENT_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)

BOUNCE_SUBJECT_PATTERNS = [
    r"delivery\s+status\s+notification\s*\(\s*failure\s*\)",
    r"undelivered\s+mail\s+returned\s+to\s+sender",
    r"mail\s+delivery\s+failed",
    r"failure\s+notice",
    r"returned\s+mail:\s*see\s+transcript\s+for\s+details",
    r"mail\s+system\s+error",
    r"message\s+undeliverable",
    r"delivery\s+failure",
    r"undeliverable:\s*",
]


def generate_tracking_token(message_id: int, salt: str = "reachy_isira_automations") -> str:
    """Generates a URL-safe hash token for a message."""
    raw = f"{message_id}:{salt}:{utcnow()[:10]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def ensure_tracking_token(db: Database, message_id: int) -> str:
    """Ensures a message row has an active tracking token."""
    row = db.fetchone("SELECT id, tracking_token FROM messages WHERE id = ?", (message_id,))
    if not row:
        raise KeyError(f"message {message_id} not found")
    if row["tracking_token"]:
        return str(row["tracking_token"])

    token = generate_tracking_token(message_id)
    db.execute(
        "UPDATE messages SET tracking_token = ?, updated_at = ? WHERE id = ?",
        (token, utcnow(), message_id),
    )
    return token


def build_tracking_pixel_tag(token: str, base_url: str = "http://localhost:8000") -> str:
    """Renders a zero-impact 1x1 transparent tracking image tag."""
    url = f"{base_url.rstrip('/')}/t/o/{token}.png"
    return (
        f'<img src="{url}" width="1" height="1" alt="" '
        'style="display:none;width:1px;height:1px;max-height:0px;max-width:0px;opacity:0;overflow:hidden;" />'
    )


def record_open_event(
    db: Database,
    token_or_id: str | int,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
    actor: str = "tracking_beacon",
) -> dict[str, Any]:
    """Records an email open event when the tracking pixel is loaded."""
    if isinstance(token_or_id, int) or (isinstance(token_or_id, str) and token_or_id.isdigit()):
        row = db.fetchone("SELECT * FROM messages WHERE id = ?", (int(token_or_id),))
    else:
        row = db.fetchone("SELECT * FROM messages WHERE tracking_token = ?", (str(token_or_id),))

    if not row:
        raise KeyError(f"message with token/id {token_or_id} not found")

    message_id = int(row["id"])
    now_iso = utcnow()
    first_open = row["opened_at"] is None
    new_count = int(row["open_count"] or 0) + 1

    with db.transaction(immediate=True) as conn:
        conn.execute(
            """UPDATE messages
               SET opened_at = COALESCE(opened_at, ?),
                   open_count = open_count + 1,
                   updated_at = ?
               WHERE id = ?""",
            (now_iso, now_iso, message_id),
        )
        conn.execute(
            """INSERT INTO message_events(message_id, event_type, detail_json, created_at)
               VALUES (?, 'OPENED', ?, ?)""",
            (
                message_id,
                json.dumps({
                    "user_agent": user_agent or "unknown",
                    "ip": ip_address or "hidden",
                    "first_open": first_open,
                    "open_number": new_count,
                }, sort_keys=True),
                now_iso,
            ),
        )

    db.audit(
        actor,
        "message.opened",
        "message",
        message_id,
        {"first_open": first_open, "open_count": new_count},
    )

    return {
        "ok": True,
        "message_id": message_id,
        "first_open": first_open,
        "open_count": new_count,
        "campaign_id": row["campaign_id"],
        "to_email": row["to_email"],
    }


def calculate_open_stats(
    db: Database,
    campaign_id: Optional[int] = None,
    account_id: Optional[int] = None,
) -> dict[str, Any]:
    """Computes total sends, unique opens, total opens, and open rate."""
    clauses = ["state IN ('SENT', 'ACCEPTED')"]
    params: list[Any] = []

    if campaign_id is not None:
        clauses.append("campaign_id = ?")
        params.append(campaign_id)
    if account_id is not None:
        clauses.append("account_id = ?")
        params.append(account_id)

    where_sql = " AND ".join(clauses)

    sent_row = db.fetchone(f"SELECT COUNT(*) AS c FROM messages WHERE {where_sql}", tuple(params))
    sent_count = int(sent_row["c"]) if sent_row else 0

    opened_row = db.fetchone(
        f"SELECT COUNT(*) AS c, SUM(open_count) AS total_opens FROM messages WHERE {where_sql} AND open_count > 0",
        tuple(params),
    )
    unique_opens = int(opened_row["c"]) if opened_row and opened_row["c"] else 0
    total_opens = int(opened_row["total_opens"]) if opened_row and opened_row["total_opens"] else 0

    open_rate = (unique_opens / sent_count) if sent_count > 0 else 0.0

    return {
        "sent_count": sent_count,
        "unique_opens": unique_opens,
        "total_opens": total_opens,
        "open_rate": round(open_rate, 4),
        "open_rate_percent": f"{open_rate * 100:.2f}%",
    }


def is_bounce_inbound(message: InboundMessage) -> bool:
    """Detects if an inbound message is a Delivery Status Notification / bounce."""
    subject = (message.subject or "").lower()
    from_addr = (message.from_email or "").lower()
    body = (message.body or "").lower()

    if any(re.search(pat, subject) for pat in BOUNCE_SUBJECT_PATTERNS):
        return True

    if from_addr.startswith(("mailer-daemon@", "postmaster@", "mail-daemon@")):
        return True

    # Check headers
    content_type = message.headers.get("content-type", "").lower()
    if "report-type=delivery-status" in content_type:
        return True

    # Check diagnostic words in body
    if "550 5.1.1" in body or "recipient address rejected" in body or "mailbox unavailable" in body:
        return True

    return False


def extract_bounced_email(message: InboundMessage) -> Optional[str]:
    """Extracts the failed recipient address from a bounce report."""
    body = f"{message.subject}\n{message.body}"
    headers_str = json.dumps(message.headers)

    # 1. Check RFC delivery status fields
    rfc_match = re.search(r"Final-Recipient:\s*(?:rfc822;)?\s*([^\s;]+@[^\s;]+)", body, re.IGNORECASE)
    if rfc_match:
        return rfc_match.group(1).strip("<>")

    orig_match = re.search(r"Original-Recipient:\s*(?:rfc822;)?\s*([^\s;]+@[^\s;]+)", body, re.IGNORECASE)
    if orig_match:
        return orig_match.group(1).strip("<>")

    # 2. Check diagnostic patterns in text
    diag_matches = re.findall(
        r"(?:failed to deliver to|could not be delivered to|recipient|to):\s*<?([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)>?",
        body,
        re.IGNORECASE,
    )
    if diag_matches:
        return diag_matches[0]

    # 3. Fallback: search for first valid email in body that is NOT the sending account or mailer-daemon
    all_emails = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", body)
    ignored = {"mailer-daemon", "postmaster", "google.com", "microsoft.com"}
    for candidate in all_emails:
        if not any(ign in candidate.lower() for ign in ignored):
            return candidate

    return None


def process_inbound_bounce_if_any(
    db: Database,
    account_id: int,
    inbound: InboundMessage,
    actor: str = "bounce_detector",
) -> Optional[dict[str, Any]]:
    """Automatically parses, suppresses, and logs bounce if the inbound message is a DSN."""
    if not is_bounce_inbound(inbound):
        return None

    bounced_recipient = extract_bounced_email(inbound)
    if not bounced_recipient:
        return {"is_bounce": True, "recipient_found": False}

    # Record hard bounce and cancel followups
    res = record_bounce(db, account_id, bounced_recipient, kind="hard", actor=actor)
    return {
        "is_bounce": True,
        "recipient_found": True,
        "recipient": bounced_recipient,
        "status": res["status"],
    }
