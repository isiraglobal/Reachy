"""Durable campaign execution with idempotency, policy gates, and recovery."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import make_msgid
from typing import Any, Callable, Optional

from .config import ReachyConfig
from .db import Database, utcnow
from .models import OutboundMessage, SendResult, parse_iso
from .normalize import normalize_domain
from .policy import PolicyEngine
from .providers.base import EmailProvider
from .sample_qc import SampleGateError, require_approved_list

TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
PERSONALIZATION_FIELDS = {"city", "state", "category", "reviews_count", "rating", "website", "phone"}
TERMINAL_SUCCESS = {"SENT", "ACCEPTED"}
TERMINAL_STOP = {"CANCELLED", "FAILED", "BLOCKED"}


class CampaignError(RuntimeError):
    pass


class TemplateError(CampaignError):
    pass


def _json(value: Optional[str]) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def handle_for(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def render_template(template: str, lead: dict[str, Any], contact: dict[str, Any]) -> str:
    values = {
        "company": lead.get("name"),
        "city": lead.get("city"),
        "state": lead.get("state"),
        "category": lead.get("category"),
        "reviews_count": lead.get("reviews_count"),
        "rating": lead.get("rating"),
        "website": lead.get("website"),
        "phone": lead.get("phone"),
        "email": contact.get("email"),
    }

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = values.get(key)
        if value in (None, ""):
            raise TemplateError(f"template variable '{{{{{key}}}}}' has no real evidence")
        return str(value)

    return TEMPLATE_RE.sub(replace, template)


def validate_personalization(template: str, require_evidence: bool = True) -> None:
    tokens = set(TEMPLATE_RE.findall(template))
    if require_evidence and not (tokens & PERSONALIZATION_FIELDS):
        raise TemplateError(
            "template requires at least one evidence variable: "
            + ", ".join(sorted(PERSONALIZATION_FIELDS))
        )


def create_campaign(
    db: Database,
    name: str,
    list_id: int,
    steps: list[dict[str, Any]],
    account_id: Optional[int] = None,
    policy: Optional[dict[str, Any]] = None,
    test_mode: bool = True,
    dry_run: bool = True,
    sender_identity: Optional[str] = None,
    target_jurisdiction: Optional[str] = None,
    actor: str = "user",
) -> int:
    if not steps:
        raise CampaignError("a campaign requires at least one step")
    if not db.fetchone("SELECT id FROM lists WHERE id = ?", (list_id,)):
        raise KeyError(f"list {list_id} not found")
    if account_id and not db.fetchone("SELECT id FROM accounts WHERE id = ?", (account_id,)):
        raise KeyError(f"account {account_id} not found")
    policy = dict(policy or {})
    now = utcnow()
    with db.transaction(immediate=True) as conn:
        campaign_id = conn.execute(
            """INSERT INTO campaigns(name, list_id, account_id, status, policy_json, test_mode,
                   dry_run, target_jurisdiction, sender_identity, created_at, updated_at)
               VALUES (?, ?, ?, 'DRAFT', ?, ?, ?, ?, ?, ?, ?)""",
            (
                name, list_id, account_id, json.dumps(policy, sort_keys=True),
                1 if test_mode else 0, 1 if dry_run else 0,
                target_jurisdiction or policy.get("jurisdiction"), sender_identity, now, now,
            ),
        ).lastrowid
        for index, step in enumerate(steps, 1):
            subject = str(step.get("subject") or "").strip()
            body = str(step.get("body") or "").strip()
            if not subject or not body:
                raise CampaignError(f"step {index} is missing a subject or body")
            conn.execute(
                """INSERT INTO campaign_steps(campaign_id, step_number, subject_template,
                       body_template, delay_days) VALUES (?, ?, ?, ?, ?)""",
                (campaign_id, index, subject, body, int(step.get("delay_days", 1))),
            )
    db.audit(actor, "campaign.created", "campaign", campaign_id, {"name": name, "list_id": list_id})
    return int(campaign_id)


def preview_campaign(db: Database, campaign_id: int, limit: int = 3) -> dict[str, Any]:
    campaign = _campaign(db, campaign_id)
    steps = db.fetchall(
        "SELECT * FROM campaign_steps WHERE campaign_id = ? ORDER BY step_number", (campaign_id,)
    )
    rows = db.fetchall(
        """SELECT l.*, c.id AS contact_id_value, c.email AS contact_email,
                  c.verification_status, c.source AS contact_source
           FROM leads l JOIN list_leads ll ON ll.lead_id = l.id
           JOIN contacts c ON c.lead_id = l.id AND c.is_primary = 1
           WHERE ll.list_id = ? ORDER BY l.id LIMIT ?""",
        (campaign["list_id"], limit),
    )
    samples = []
    policy = _json(campaign["policy_json"])
    require_evidence = policy.get("require_personalization_evidence", True)
    for row in rows:
        lead = dict(row)
        contact = {"email": row["contact_email"]}
        try:
            step = steps[0]
            subject = render_template(step["subject_template"], lead, contact)
            body = render_template(step["body_template"], lead, contact)
            validate_personalization(step["body_template"], require_evidence)
            error = None
        except TemplateError as exc:
            subject, body, error = "", "", str(exc)
        samples.append(
            {
                "company": lead["name"],
                "to_email": contact["email"],
                "verification_status": row["verification_status"],
                "subject": subject,
                "body": body,
                "error": error,
            }
        )
    return {
        "campaign": campaign["name"],
        "status": campaign["status"],
        "test_mode": bool(campaign["test_mode"]),
        "dry_run": bool(campaign["dry_run"]),
        "samples": samples,
    }


def approve_campaign(
    db: Database,
    campaign_id: int,
    approved_by: str,
    notes: str = "",
    config: Optional[ReachyConfig] = None,
) -> dict[str, Any]:
    campaign = _campaign(db, campaign_id)
    require_approved_list(db, int(campaign["list_id"]))
    steps = db.fetchall("SELECT * FROM campaign_steps WHERE campaign_id = ?", (campaign_id,))
    if not steps:
        raise CampaignError("campaign has no steps")
    policy = _json(campaign["policy_json"])
    missing = []
    if not str(policy.get("jurisdiction") or "").strip():
        missing.append("jurisdiction")
    if not str(policy.get("lawful_basis") or "").strip():
        missing.append("lawful_basis")
    if not policy.get("policy_reviewed"):
        missing.append("policy_reviewed=true")
    if not str(campaign.get("sender_identity") or "").strip():
        missing.append("sender_identity")
    if missing:
        raise CampaignError("campaign policy is incomplete: " + ", ".join(missing))
    if not campaign["dry_run"]:
        account = db.fetchone("SELECT * FROM accounts WHERE id = ?", (campaign["account_id"],))
        if not account or account["status"] != "ACTIVE" or not account["authorized_at"]:
            raise CampaignError("a live campaign requires an active authorized sending account")
        if campaign["test_mode"] and not (config and config.test_recipient):
            raise CampaignError("test mode requires REACHY_TEST_RECIPIENT")
    require_evidence = policy.get("require_personalization_evidence", True)
    for step in steps:
        validate_personalization(step["body_template"], require_evidence)
    preview = preview_campaign(db, campaign_id, limit=1)
    if preview["samples"] and preview["samples"][0].get("error"):
        raise CampaignError(f"template preview failed: {preview['samples'][0]['error']}")
    now = utcnow()
    with db.transaction(immediate=True) as conn:
        conn.execute(
            "UPDATE campaigns SET status='APPROVED', approved_at=?, approved_by=?, updated_at=? WHERE id=?",
            (now, approved_by, now, campaign_id),
        )
    db.audit(approved_by, "campaign.approved", "campaign", campaign_id, {"notes": notes})
    return {"campaign_id": campaign_id, "status": "APPROVED", "approved_at": now}


def _campaign(db: Database, campaign_id: int) -> dict[str, Any]:
    row = db.fetchone("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    if not row:
        raise KeyError(f"campaign {campaign_id} not found")
    return dict(row)


def _idempotency_key(campaign_id: int, contact_id: int, step: int) -> str:
    return hashlib.sha256(f"{campaign_id}:{contact_id}:{step}".encode("utf-8")).hexdigest()


def _primary_contacts(db: Database, list_id: int) -> list[dict[str, Any]]:
    rows = db.fetchall(
        """SELECT l.*, c.id AS contact_id, c.email AS contact_email,
                  c.verification_status, c.source AS contact_source
           FROM leads l JOIN list_leads ll ON ll.lead_id = l.id
           JOIN contacts c ON c.lead_id = l.id AND c.is_primary = 1
           WHERE ll.list_id = ?
           ORDER BY l.id""",
        (list_id,),
    )
    return [dict(row) for row in rows]


def start_campaign(
    db: Database,
    campaign_id: int,
    config: ReachyConfig,
    actor: str = "user",
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    campaign = _campaign(db, campaign_id)
    if campaign["status"] not in {"APPROVED", "PAUSED"}:
        raise CampaignError(f"campaign must be APPROVED to start (status={campaign['status']})")
    require_approved_list(db, int(campaign["list_id"]))
    if not campaign.get("approved_at"):
        raise CampaignError("campaign has not been approved")
    steps = db.fetchall(
        "SELECT * FROM campaign_steps WHERE campaign_id = ? ORDER BY step_number", (campaign_id,)
    )
    if not steps:
        raise CampaignError("campaign has no steps")
    policy = _json(campaign["policy_json"])
    require_evidence = policy.get("require_personalization_evidence", True)
    contacts = _primary_contacts(db, int(campaign["list_id"]))
    if not contacts:
        raise CampaignError("list has no primary contacts to plan")
    base = now or datetime.now(timezone.utc)
    planned = 0
    blocked = 0
    now_iso = utcnow()
    with db.transaction(immediate=True) as conn:
        for contact in contacts:
            cumulative = base
            for step in steps:
                if int(step["step_number"]) > 1:
                    cumulative = cumulative + timedelta(days=int(step["delay_days"]))
                contact_stub = {"email": contact["contact_email"]}
                state = "PLANNED"
                last_error = None
                try:
                    subject = render_template(step["subject_template"], contact, contact_stub)
                    body = render_template(step["body_template"], contact, contact_stub)
                    validate_personalization(step["body_template"], require_evidence)
                    body = body.rstrip() + "\n\n" + config.unsubscribe_footer
                except TemplateError as exc:
                    subject, body, state, last_error = "", "", "BLOCKED", str(exc)
                message_id_header = make_msgid(domain=normalize_domain(contact["contact_email"]) or "reachy.local")
                conn.execute(
                    """INSERT OR IGNORE INTO messages(
                           campaign_id, lead_id, contact_id, account_id, step_number, state,
                           idempotency_key, from_email, to_email, subject, body,
                           message_id_header, scheduled_at, last_error, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        campaign_id, contact["id"], contact["contact_id"], campaign["account_id"],
                        step["step_number"], state,
                        _idempotency_key(campaign_id, contact["contact_id"], step["step_number"]),
                        _account_email(db, campaign["account_id"]),
                        contact["contact_email"], subject, body, message_id_header,
                        cumulative.isoformat(), last_error, now_iso, now_iso,
                    ),
                )
                if state == "BLOCKED":
                    blocked += 1
                else:
                    planned += 1
        conn.execute(
            """UPDATE campaigns SET status='RUNNING', started_at=COALESCE(started_at, ?),
                   updated_at=? WHERE id=?""",
            (now_iso, now_iso, campaign_id),
        )
    db.audit(actor, "campaign.started", "campaign", campaign_id, {"planned": planned, "blocked": blocked})
    return {"campaign_id": campaign_id, "status": "RUNNING", "planned": planned, "blocked": blocked}


def _account_email(db: Database, account_id: Optional[int]) -> Optional[str]:
    if not account_id:
        return None
    row = db.fetchone("SELECT email FROM accounts WHERE id = ?", (account_id,))
    return row["email"] if row else None


def pause_campaign(db: Database, campaign_id: int, actor: str = "user") -> None:
    db.execute(
        "UPDATE campaigns SET status='PAUSED', paused_at=?, updated_at=? WHERE id=?",
        (utcnow(), utcnow(), campaign_id),
    )
    db.audit(actor, "campaign.paused", "campaign", campaign_id)


def resume_campaign(db: Database, campaign_id: int, actor: str = "user") -> None:
    campaign = _campaign(db, campaign_id)
    if campaign["status"] != "PAUSED":
        raise CampaignError(f"campaign is not paused (status={campaign['status']})")
    require_approved_list(db, int(campaign["list_id"]))
    db.execute(
        "UPDATE campaigns SET status='RUNNING', paused_at=NULL, updated_at=? WHERE id=?",
        (utcnow(), campaign_id),
    )
    db.audit(actor, "campaign.resumed", "campaign", campaign_id)


def stop_campaign(db: Database, campaign_id: int, actor: str = "user", reason: str = "stopped") -> None:
    now = utcnow()
    with db.transaction(immediate=True) as conn:
        conn.execute(
            "UPDATE campaigns SET status='STOPPED', completed_at=?, updated_at=? WHERE id=?",
            (now, now, campaign_id),
        )
        conn.execute(
            """UPDATE messages SET state='CANCELLED', cancelled_at=?, updated_at=?
               WHERE campaign_id=? AND state IN ('PLANNED','QUEUED')""",
            (now, now, campaign_id),
        )
    db.audit(actor, "campaign.stopped", "campaign", campaign_id, {"reason": reason})


def set_global_pause(db: Database, paused: bool, actor: str = "user") -> None:
    db.set_setting("global_pause", "1" if paused else "0")
    db.audit(actor, "global_pause." + ("enabled" if paused else "disabled"))


def cancel_followups(
    db: Database,
    contact_id: int,
    campaign_id: Optional[int] = None,
    reason: str = "reply",
    actor: str = "system",
) -> int:
    now = utcnow()
    if campaign_id is not None:
        sql = """UPDATE messages SET state='CANCELLED', cancelled_at=?, updated_at=?
                 WHERE contact_id=? AND campaign_id=? AND step_number > 1
                   AND state IN ('PLANNED','QUEUED')"""
        params = (now, now, contact_id, campaign_id)
    else:
        sql = """UPDATE messages SET state='CANCELLED', cancelled_at=?, updated_at=?
                 WHERE contact_id=? AND step_number > 1 AND state IN ('PLANNED','QUEUED')"""
        params = (now, now, contact_id)
    cursor = db.execute(sql, params)
    if cursor.rowcount:
        db.audit(actor, "followups.cancelled", "contact", contact_id, {"reason": reason, "count": cursor.rowcount})
    return int(cursor.rowcount)


class CampaignWorker:
    def __init__(
        self,
        db: Database,
        config: ReachyConfig,
        provider_factory: Callable[[dict[str, Any]], EmailProvider],
        worker_id: str = "worker",
        policy: Optional[PolicyEngine] = None,
    ):
        self.db = db
        self.config = config
        self.provider_factory = provider_factory
        self.worker_id = worker_id
        self.policy = policy or PolicyEngine(config)

    def run_once(self, max_messages: int = 25, now: Optional[datetime] = None) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        summary = {"processed": 0, "sent": 0, "failed": 0, "uncertain": 0, "blocked": 0, "dry_run": 0, "noop": 0}
        if self.db.get_setting("global_pause", "0") == "1":
            summary["noop"] = 1
            summary["reason"] = "global_pause"
            return summary
        self._promote_due(now)
        for _ in range(max_messages):
            message = self._claim(now)
            if not message:
                break
            outcome = self._process(message, now)
            summary["processed"] += 1
            summary[outcome] = summary.get(outcome, 0) + 1
        return summary

    def _promote_due(self, now: datetime) -> None:
        rows = self.db.fetchall(
            """SELECT m.* FROM messages m JOIN campaigns c ON c.id = m.campaign_id
               WHERE m.state='PLANNED' AND m.scheduled_at <= ? AND c.status='RUNNING'
               ORDER BY m.scheduled_at LIMIT 500""",
            (now.isoformat(),),
        )
        for row in rows:
            previous = None
            if int(row["step_number"]) > 1:
                previous = self.db.fetchone(
                    """SELECT state FROM messages WHERE campaign_id=? AND contact_id=? AND step_number=?""",
                    (row["campaign_id"], row["contact_id"], int(row["step_number"]) - 1),
                )
            if previous is None or previous["state"] in TERMINAL_SUCCESS:
                self.db.execute(
                    "UPDATE messages SET state='QUEUED', updated_at=? WHERE id=? AND state='PLANNED'",
                    (utcnow(), row["id"]),
                )
                self._event(int(row["id"]), "QUEUED")
            elif previous["state"] in TERMINAL_STOP:
                self.db.execute(
                    """UPDATE messages SET state='CANCELLED', cancelled_at=?, updated_at=?,
                           last_error=? WHERE id=? AND state='PLANNED'""",
                    (utcnow(), utcnow(), f"previous step {previous['state'].lower()}", row["id"]),
                )
                self._event(int(row["id"]), "CANCELLED", {"reason": "previous step did not succeed"})

    def _claim(self, now: datetime) -> Optional[dict[str, Any]]:
        with self.db.transaction(immediate=True) as conn:
            row = conn.execute(
                """SELECT m.* FROM messages m JOIN campaigns c ON c.id = m.campaign_id
                   WHERE m.state='QUEUED' AND m.scheduled_at <= ? AND c.status='RUNNING'
                   ORDER BY m.scheduled_at, m.id LIMIT 1""",
                (now.isoformat(),),
            ).fetchone()
            if not row:
                return None
            updated = conn.execute(
                """UPDATE messages SET state='SENDING', attempts=attempts+1, updated_at=?
                   WHERE id=? AND state='QUEUED'""",
                (utcnow(), row["id"]),
            )
            if updated.rowcount != 1:
                return None
            return dict(row)

    def _process(self, message: dict[str, Any], now: datetime) -> str:
        campaign = _campaign(self.db, int(message["campaign_id"]))
        message = dict(message)
        message["to_email"] = message["to_email"]
        decision = self.policy.check_send(self.db, message)
        if not decision.allowed:
            self.db.execute(
                """UPDATE messages SET state='BLOCKED', policy_snapshot=?, last_error=?, updated_at=?
                   WHERE id=?""",
                (
                    json.dumps(decision.as_dict(), sort_keys=True),
                    "; ".join(decision.reasons[:5]),
                    utcnow(),
                    message["id"],
                ),
            )
            self._event(int(message["id"]), "BLOCKED", {"reasons": decision.reasons})
            return "blocked"

        if campaign["dry_run"]:
            self.db.execute(
                """UPDATE messages SET state='SKIPPED', policy_snapshot=?, last_error=?,
                       updated_at=? WHERE id=?""",
                (json.dumps(decision.as_dict(), sort_keys=True), "dry_run: not submitted", utcnow(), message["id"]),
            )
            self._event(int(message["id"]), "DRY_RUN", {"to": message["to_email"]})
            return "dry_run"

        account = self.db.fetchone("SELECT * FROM accounts WHERE id = ?", (message["account_id"],))
        if not account:
            self.db.execute(
                "UPDATE messages SET state='BLOCKED', last_error=?, updated_at=? WHERE id=?",
                ("sending account missing", utcnow(), message["id"]),
            )
            self._event(int(message["id"]), "BLOCKED", {"reason": "sending account missing"})
            return "blocked"
        if not self._reserve_quota(int(account["id"])):
            self.db.execute(
                """UPDATE messages SET state='BLOCKED', last_error=?, updated_at=? WHERE id=?""",
                ("daily sending limit reached", utcnow(), message["id"]),
            )
            self._event(int(message["id"]), "BLOCKED", {"reason": "daily sending limit"})
            return "blocked"

        to_email = message["to_email"]
        if campaign["test_mode"]:
            to_email = self.config.test_recipient or ""
            if not to_email:
                self.db.execute(
                    "UPDATE messages SET state='BLOCKED', last_error=?, updated_at=? WHERE id=?",
                    ("test mode requires REACHY_TEST_RECIPIENT", utcnow(), message["id"]),
                )
                self._event(int(message["id"]), "BLOCKED", {"reason": "missing test recipient"})
                return "blocked"

        try:
            provider = self.provider_factory(dict(account))
        except Exception as exc:  # noqa: BLE001
            error = f"{exc.__class__.__name__}: {exc}"
            self.db.execute(
                """UPDATE messages SET state='FAILED', policy_snapshot=?, last_error=?, updated_at=?
                   WHERE id=?""",
                (json.dumps(decision.as_dict(), sort_keys=True), error, utcnow(), message["id"]),
            )
            self._event(int(message["id"]), "PROVIDER_ERROR", {"error": error})
            return "failed"

        outbound = OutboundMessage(
            from_email=account["email"],
            from_name=account["display_name"] or "",
            to_email=to_email,
            subject=message["subject"],
            body=message["body"],
            message_id_header=message["message_id_header"],
            headers={
                "X-Reachy-Campaign": str(message["campaign_id"]),
                "X-Reachy-Message": str(message["id"]),
            },
            campaign_id=int(message["campaign_id"]),
            contact_id=int(message["contact_id"]),
            message_row_id=int(message["id"]),
        )
        try:
            result = provider.send(outbound)
        except Exception as exc:  # noqa: BLE001
            result = SendResult("uncertain", error=f"{exc.__class__.__name__}: {exc}", retryable=True)
        finally:
            provider.close()

        snapshot = json.dumps(decision.as_dict(), sort_keys=True)
        if result.status == "accepted":
            now_iso = utcnow()
            self.db.execute(
                """UPDATE messages SET state='SENT', accepted_at=?, sent_at=?, provider_message_id=?,
                       policy_snapshot=?, last_error=NULL, updated_at=? WHERE id=?""",
                (now_iso, now_iso, result.provider_message_id, snapshot, now_iso, message["id"]),
            )
            self._event(int(message["id"]), "SENT", {"provider_message_id": result.provider_message_id})
            self._maybe_complete(int(message["campaign_id"]))
            return "sent"
        if result.status == "uncertain":
            self.db.execute(
                """UPDATE messages SET state='UNCERTAIN', policy_snapshot=?, last_error=?, updated_at=?
                   WHERE id=?""",
                (snapshot, result.error, utcnow(), message["id"]),
            )
            self._event(int(message["id"]), "UNCERTAIN", {"error": result.error})
            return "uncertain"
        self.db.execute(
            """UPDATE messages SET state='FAILED', policy_snapshot=?, last_error=?, updated_at=?
               WHERE id=?""",
            (snapshot, result.error, utcnow(), message["id"]),
        )
        self._event(int(message["id"]), "FAILED", {"error": result.error})
        if result.error and "auth" in result.error.lower():
            self.db.execute(
                "UPDATE accounts SET status='ERROR', last_error=?, updated_at=? WHERE id=?",
                (result.error, utcnow(), account["id"]),
            )
        return "failed"

    def _reserve_quota(self, account_id: int) -> bool:
        today = datetime.now(timezone.utc).date().isoformat()
        with self.db.transaction(immediate=True) as conn:
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
            if not row:
                return False
            if row["sends_today_date"] != today:
                conn.execute(
                    "UPDATE accounts SET sends_today=0, sends_today_date=? WHERE id=?",
                    (today, account_id),
                )
            updated = conn.execute(
                """UPDATE accounts SET sends_today=sends_today+1, sends_today_date=?
                   WHERE id=? AND sends_today < daily_limit""",
                (today, account_id),
            )
            return updated.rowcount == 1

    def _event(self, message_id: int, event_type: str, detail: Optional[dict[str, Any]] = None) -> None:
        self.db.execute(
            "INSERT INTO message_events(message_id, event_type, detail_json, created_at) VALUES (?, ?, ?, ?)",
            (message_id, event_type, json.dumps(detail, sort_keys=True) if detail else None, utcnow()),
        )

    def _maybe_complete(self, campaign_id: int) -> None:
        row = self.db.fetchone(
            """SELECT COUNT(*) AS remaining FROM messages
               WHERE campaign_id=? AND state IN ('PLANNED','QUEUED','SENDING')""",
            (campaign_id,),
        )
        if row and int(row["remaining"]) == 0:
            self.db.execute(
                "UPDATE campaigns SET status='COMPLETED', completed_at=?, updated_at=? WHERE id=?",
                (utcnow(), utcnow(), campaign_id),
            )
            self.db.audit(self.worker_id, "campaign.completed", "campaign", campaign_id)


def reconcile_campaign(
    db: Database,
    campaign_id: int,
    provider_factory: Callable[[dict[str, Any]], EmailProvider],
    config: ReachyConfig,
    actor: str = "worker",
) -> dict[str, int]:
    rows = db.fetchall(
        "SELECT * FROM messages WHERE campaign_id=? AND state IN ('UNCERTAIN','SENDING')",
        (campaign_id,),
    )
    outcome = {"found": 0, "failed": 0, "still_uncertain": 0}
    campaign = _campaign(db, campaign_id)
    policy = _json(campaign["policy_json"])
    allow_retry = bool(policy.get("allow_retry_after_not_found", False))
    now = datetime.now(timezone.utc)
    for row in rows:
        account = db.fetchone("SELECT * FROM accounts WHERE id = ?", (row["account_id"],))
        if not account:
            continue
        try:
            provider = provider_factory(dict(account))
            try:
                provider_id = provider.find_by_message_id(row["message_id_header"])
            finally:
                provider.close()
        except Exception as exc:  # noqa: BLE001
            db.audit(
                actor,
                "message.reconcile_error",
                "message",
                row["id"],
                {"error": f"{exc.__class__.__name__}: {exc}"},
            )
            outcome["still_uncertain"] += 1
            continue
        if provider_id:
            db.execute(
                """UPDATE messages SET state='SENT', provider_message_id=?, accepted_at=COALESCE(accepted_at, ?),
                       sent_at=COALESCE(sent_at, ?), last_error=NULL, updated_at=? WHERE id=?""",
                (provider_id, utcnow(), utcnow(), utcnow(), row["id"]),
            )
            db.audit(actor, "message.reconciled_sent", "message", row["id"], {"provider_id": provider_id})
            outcome["found"] += 1
        else:
            age = now - parse_iso(row["updated_at"])
            if age.total_seconds() < config.reconcile_grace_seconds:
                outcome["still_uncertain"] += 1
                continue
            if allow_retry:
                db.execute(
                    "UPDATE messages SET state='QUEUED', last_error=?, updated_at=? WHERE id=?",
                    ("reconciled not found; retry permitted by campaign policy", utcnow(), row["id"]),
                )
            else:
                db.execute(
                    "UPDATE messages SET state='FAILED', last_error=?, updated_at=? WHERE id=?",
                    ("not found at provider after grace period; not retried", utcnow(), row["id"]),
                )
            db.audit(actor, "message.reconciled_failed", "message", row["id"])
            outcome["failed"] += 1
    return outcome
