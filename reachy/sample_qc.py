"""Reproducible sample-first quality control and list approval."""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Optional

from .db import Database, utcnow


class SampleGateError(RuntimeError):
    pass


def _sample_seed(list_id: int, count: int) -> int:
    digest = hashlib.sha256(f"reachy-sample:{list_id}:{count}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _lead_records(db: Database, list_id: int) -> list[dict[str, Any]]:
    rows = db.fetchall(
        """SELECT l.* FROM leads l
           JOIN list_leads ll ON ll.lead_id = l.id
           WHERE ll.list_id = ?
           ORDER BY l.id""",
        (list_id,),
    )
    records = []
    for row in rows:
        lead = dict(row)
        contact = db.fetchone(
            """SELECT * FROM contacts WHERE lead_id = ?
               ORDER BY is_primary DESC, id ASC LIMIT 1""",
            (lead["id"],),
        )
        records.append(
            {
                "lead_id": int(lead["id"]),
                "company": lead["name"],
                "website": lead["website"],
                "contact_email": contact["email"] if contact else None,
                "contact_source": contact["source"] if contact else None,
                "discovery_method": contact["discovery_method"] if contact else None,
                "verification_status": contact["verification_status"] if contact else "missing",
                "source": lead["source"],
                "source_url": lead["source_url"],
                "qualification_score": lead["qualification_score"],
                "qualification_reason": lead["qualification_reason"],
                "qualification_evidence": json.loads(lead["qualification_evidence"] or "[]"),
                "flags": json.loads(lead["flags_json"] or "[]"),
            }
        )
    return records


def create_sample(
    db: Database,
    list_id: int,
    size: int = 10,
    seed: Optional[int] = None,
    threshold: int = 2,
    actor: str = "system",
) -> dict[str, Any]:
    listing = db.fetchone("SELECT * FROM lists WHERE id = ?", (list_id,))
    if not listing:
        raise KeyError(f"list {list_id} not found")
    records = _lead_records(db, list_id)
    if not records:
        raise SampleGateError("cannot sample an empty list")
    if size < 1:
        raise ValueError("sample size must be at least 1")
    chosen_seed = seed if seed is not None else _sample_seed(list_id, len(records))
    rng = random.Random(chosen_seed)
    sample = rng.sample(records, min(size, len(records)))
    now = utcnow()
    with db.transaction(immediate=True) as conn:
        conn.execute("DELETE FROM list_approvals WHERE list_id = ?", (list_id,))
        review_id = conn.execute(
            """INSERT INTO sample_reviews(list_id, seed, sample_json, threshold, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (list_id, chosen_seed, json.dumps(sample, sort_keys=True), threshold, now),
        ).lastrowid
        conn.execute(
            "UPDATE lists SET status='SAMPLE_READY', updated_at=? WHERE id=?",
            (now, list_id),
        )
    db.audit(actor, "sample.created", "list", list_id, {"review_id": review_id, "seed": chosen_seed})
    return {
        "review_id": int(review_id),
        "list_id": list_id,
        "seed": chosen_seed,
        "threshold": threshold,
        "sample_size": len(sample),
        "records": sample,
    }


def record_review(
    db: Database,
    review_id: int,
    incorrect_indices: list[int],
    notes: str = "",
    reviewer: str = "user",
) -> dict[str, Any]:
    review = db.fetchone("SELECT * FROM sample_reviews WHERE id = ?", (review_id,))
    if not review:
        raise KeyError(f"sample review {review_id} not found")
    if review["decision"] is not None:
        raise SampleGateError("this sample has already been reviewed")
    sample = json.loads(review["sample_json"])
    indices = sorted({int(i) for i in incorrect_indices})
    for index in indices:
        if index < 1 or index > len(sample):
            raise ValueError(f"sample index out of range: {index}")
    incorrect = len(indices)
    threshold = int(review["threshold"])
    rejected = incorrect >= threshold
    failure_pattern = _failure_pattern(sample, indices, notes)
    decisions = [
        {
            "index": i + 1,
            "company": record["company"],
            "correct": (i + 1) not in indices,
        }
        for i, record in enumerate(sample)
    ]
    now = utcnow()
    with db.transaction(immediate=True) as conn:
        conn.execute(
            """UPDATE sample_reviews SET incorrect_count=?, decision=?, reviewer=?, notes=?,
                   failure_pattern=?, decisions_json=? WHERE id=?""",
            (
                incorrect,
                "REJECTED" if rejected else "APPROVED",
                reviewer,
                notes,
                failure_pattern,
                json.dumps(decisions, sort_keys=True),
                review_id,
            ),
        )
        conn.execute(
            "UPDATE lists SET status=?, updated_at=? WHERE id=?",
            ("BLOCKED" if rejected else "SAMPLE_READY", now, review["list_id"]),
        )
        conn.execute("DELETE FROM list_approvals WHERE list_id = ?", (review["list_id"],))
    db.audit(
        reviewer,
        "sample.reviewed",
        "list",
        review["list_id"],
        {"review_id": review_id, "incorrect": incorrect, "threshold": threshold, "decision": "REJECTED" if rejected else "APPROVED"},
    )
    return {
        "review_id": review_id,
        "list_id": int(review["list_id"]),
        "incorrect_count": incorrect,
        "threshold": threshold,
        "decision": "REJECTED" if rejected else "APPROVED",
        "failure_pattern": failure_pattern,
        "records": decisions,
    }


def _failure_pattern(sample: list[dict], indices: list[int], notes: str) -> str:
    if not indices:
        return notes or "No incorrect records in this sample."
    reasons = {record.get("verification_status", "unknown") for record in (sample[i - 1] for i in indices)}
    missing = sum(1 for i in indices if not sample[i - 1].get("contact_email"))
    parts = [f"incorrect records: {', '.join(str(i) for i in indices)}"]
    if missing:
        parts.append(f"{missing} missing contact email(s)")
    parts.append(f"verification states: {', '.join(sorted(reasons))}")
    if notes:
        parts.append(f"reviewer notes: {notes}")
    return "; ".join(parts)


def approve_list(
    db: Database,
    list_id: int,
    approved_by: str,
    notes: str = "",
) -> dict[str, Any]:
    listing = db.fetchone("SELECT * FROM lists WHERE id = ?", (list_id,))
    if not listing:
        raise KeyError(f"list {list_id} not found")
    review = db.fetchone(
        "SELECT * FROM sample_reviews WHERE list_id = ? ORDER BY id DESC LIMIT 1", (list_id,)
    )
    if not review:
        raise SampleGateError("no sample review exists; create and review a sample first")
    if review["decision"] != "APPROVED":
        raise SampleGateError("latest sample review is not approved")
    if int(review["incorrect_count"] or 0) >= int(review["threshold"]):
        raise SampleGateError("incorrect sample count meets or exceeds the configured threshold")
    now = utcnow()
    with db.transaction(immediate=True) as conn:
        conn.execute(
            """INSERT INTO list_approvals(list_id, sample_review_id, approved_by, approved_at, notes)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(list_id) DO UPDATE SET sample_review_id=excluded.sample_review_id,
                   approved_by=excluded.approved_by, approved_at=excluded.approved_at, notes=excluded.notes""",
            (list_id, review["id"], approved_by, now, notes),
        )
        conn.execute("UPDATE lists SET status='APPROVED', updated_at=? WHERE id=?", (now, list_id))
    db.audit(approved_by, "list.approved", "list", list_id, {"review_id": review["id"]})
    return {"list_id": list_id, "status": "APPROVED", "review_id": int(review["id"]), "approved_at": now}


def require_approved_list(db: Database, list_id: int) -> None:
    listing = db.fetchone("SELECT status FROM lists WHERE id = ?", (list_id,))
    if not listing:
        raise SampleGateError(f"list {list_id} not found")
    if listing["status"] != "APPROVED":
        raise SampleGateError(f"list {list_id} is not approved (status={listing['status']})")
    approval = db.fetchone("SELECT id FROM list_approvals WHERE list_id = ?", (list_id,))
    if not approval:
        raise SampleGateError(f"list {list_id} has no approval record")
