"""Global suppression list. Persists across campaigns, imports and restarts."""

from __future__ import annotations

from typing import Optional

from .db import Database, utcnow
from .normalize import is_valid_email_syntax, normalize_email

REASON_PRECEDENCE = {
    "manual": 1,
    "legal": 2,
    "unsubscribe": 3,
    "hard_bounce": 4,
    "complaint": 5,
}


def add_suppression(
    db: Database,
    email: str,
    reason: str,
    source: Optional[str] = None,
    campaign_id: Optional[int] = None,
    notes: Optional[str] = None,
    actor: str = "system",
) -> bool:
    """Add or upgrade a suppression entry. Returns True if newly added."""
    normalized = normalize_email(email)
    if not is_valid_email_syntax(normalized):
        raise ValueError(f"invalid email for suppression: {email!r}")
    if reason not in REASON_PRECEDENCE:
        raise ValueError(f"invalid suppression reason: {reason}")
    existing = db.fetchone(
        "SELECT id, reason FROM suppression WHERE normalized_email = ?", (normalized,)
    )
    now = utcnow()
    if existing:
        if REASON_PRECEDENCE[reason] > REASON_PRECEDENCE.get(existing["reason"], 0):
            db.execute(
                "UPDATE suppression SET reason=?, source=?, campaign_id=?, notes=?, created_at=? WHERE id=?",
                (reason, source, campaign_id, notes, now, existing["id"]),
            )
            db.audit(actor, "suppression.upgraded", "suppression", existing["id"], {"reason": reason})
        return False
    suppression_id = db.insert(
        """INSERT INTO suppression(email, normalized_email, reason, source, campaign_id, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (email.strip(), normalized, reason, source, campaign_id, notes, now),
    )
    db.audit(actor, "suppression.added", "suppression", suppression_id, {"reason": reason})
    return True


def remove_suppression(
    db: Database, email: str, actor: str = "user", force: bool = False
) -> bool:
    """Remove a suppression record, with a guard for legally significant reasons.

    Unsubscribe, complaint, and legal suppressions require an explicit force
    decision after review. Hard-bounce and manual records can be corrected
    without it.
    """
    normalized = normalize_email(email)
    row = db.fetchone(
        "SELECT id, reason FROM suppression WHERE normalized_email = ?", (normalized,)
    )
    if not row:
        return False
    if row["reason"] in {"unsubscribe", "complaint", "legal"} and not force:
        raise ValueError(
            f"suppression reason '{row['reason']}' requires --force after legal review"
        )
    db.execute("DELETE FROM suppression WHERE id = ?", (row["id"],))
    db.audit(
        actor,
        "suppression.removed",
        "suppression",
        row["id"],
        {"email": normalized, "reason": row["reason"], "forced": bool(force)},
    )
    return True


def is_suppressed(db: Database, email: str) -> Optional[dict]:
    normalized = normalize_email(email)
    row = db.fetchone("SELECT * FROM suppression WHERE normalized_email = ?", (normalized,))
    return dict(row) if row else None


def list_suppression(db: Database, limit: int = 500) -> list[dict]:
    rows = db.fetchall("SELECT * FROM suppression ORDER BY created_at DESC LIMIT ?", (limit,))
    return [dict(row) for row in rows]
