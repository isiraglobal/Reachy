"""Sender health monitoring and automatic pause signals.

Reachy reports accepted messages, failures, bounces, complaints, unsubscribes,
replies, queue failures, and synchronization delay. It does NOT claim inbox
placement or delivery without an actual provider event.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from .db import Database, utcnow


@dataclass
class HealthThresholds:
    min_sample: int = 20
    bounce_rate: float = 0.05
    complaint_rate: float = 0.001
    failure_rate: float = 0.10
    sync_lag_seconds: int = 6 * 3600


@dataclass
class HealthReport:
    account_id: int
    email: str
    metrics: dict[str, Any]
    rates: dict[str, Optional[float]]
    alerts: list[str]
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "email": self.email,
            "metrics": self.metrics,
            "rates": self.rates,
            "alerts": self.alerts,
            "status": self.status,
            "delivered": None,
            "inbox_placement": None,
            "note": "Delivery and placement are not claimed without provider events.",
        }


def compute_health(
    db: Database,
    account_id: int,
    days: int = 14,
    now: Optional[datetime] = None,
    thresholds: Optional[HealthThresholds] = None,
    provider_check: Optional[Callable[[], tuple[bool, str]]] = None,
) -> HealthReport:
    thresholds = thresholds or HealthThresholds()
    now = now or datetime.now(timezone.utc)
    window_start = (now - timedelta(days=days)).isoformat()
    account = db.fetchone("SELECT * FROM accounts WHERE id = ?", (account_id,))
    if not account:
        raise KeyError(f"account {account_id} not found")

    messages = db.fetchall(
        """SELECT state, COUNT(*) AS c FROM messages
           WHERE account_id=? AND created_at >= ? GROUP BY state""",
        (account_id, window_start),
    )
    counts = {row["state"]: int(row["c"]) for row in messages}
    accepted = counts.get("SENT", 0) + counts.get("ACCEPTED", 0)
    failed = counts.get("FAILED", 0)
    uncertain = counts.get("UNCERTAIN", 0)
    blocked = counts.get("BLOCKED", 0)

    bounces = _event_count(db, account_id, "HARD_BOUNCE", window_start)
    complaints = _event_count(db, account_id, "COMPLAINT", window_start)
    unsubscribes = _event_count(db, account_id, "UNSUBSCRIBE", window_start)
    replies = db.fetchone(
        "SELECT COUNT(*) AS c FROM replies WHERE account_id=? AND created_at >= ?",
        (account_id, window_start),
    )
    positive = db.fetchone(
        """SELECT COUNT(*) AS c FROM replies WHERE account_id=? AND created_at >= ?
           AND classification IN ('interested','referral')""",
        (account_id, window_start),
    )
    reply_count = int(replies["c"]) if replies else 0
    positive_count = int(positive["c"]) if positive else 0

    last_sync = account["last_sync_at"]
    sync_lag = None
    if last_sync:
        try:
            sync_lag = max(0.0, (now - datetime.fromisoformat(last_sync)).total_seconds())
        except ValueError:
            sync_lag = None

    auth_ok = account["status"] == "ACTIVE"
    auth_detail = f"account status {account['status']}"
    if provider_check:
        auth_ok, auth_detail = provider_check()

    base = accepted + failed
    bounce_rate = (bounces / accepted) if accepted else None
    complaint_rate = (complaints / accepted) if accepted else None
    failure_rate = (failed / base) if base else None
    alerts: list[str] = []
    if base >= thresholds.min_sample and failure_rate is not None and failure_rate > thresholds.failure_rate:
        alerts.append(f"failure_rate {failure_rate:.2%} exceeds {thresholds.failure_rate:.2%}")
    if accepted >= thresholds.min_sample and bounce_rate is not None and bounce_rate > thresholds.bounce_rate:
        alerts.append(f"bounce_rate {bounce_rate:.2%} exceeds {thresholds.bounce_rate:.2%}")
    if accepted >= thresholds.min_sample and complaint_rate is not None and complaint_rate > thresholds.complaint_rate:
        alerts.append(f"complaint_rate {complaint_rate:.2%} exceeds {thresholds.complaint_rate:.2%}")
    if not auth_ok:
        alerts.append(f"authentication/connectivity failure: {auth_detail}")
    if sync_lag is not None and sync_lag > thresholds.sync_lag_seconds:
        alerts.append(f"reply sync lag {int(sync_lag)}s exceeds {thresholds.sync_lag_seconds}s")

    return HealthReport(
        account_id=account_id,
        email=account["email"],
        metrics={
            "attempted": accepted + failed + uncertain,
            "accepted": accepted,
            "failed": failed,
            "uncertain": uncertain,
            "blocked": blocked,
            "bounces": bounces,
            "complaints": complaints,
            "unsubscribes": unsubscribes,
            "replies": reply_count,
            "positive_replies": positive_count,
            "queue_failures": failed,
            "sync_lag_seconds": sync_lag,
            "authentication_ok": auth_ok,
            "authentication_detail": auth_detail,
            "window_days": days,
        },
        rates={
            "bounce_rate": bounce_rate,
            "complaint_rate": complaint_rate,
            "failure_rate": failure_rate,
            "reply_rate": (reply_count / accepted) if accepted else None,
            "positive_reply_rate": (positive_count / accepted) if accepted else None,
        },
        alerts=alerts,
        status="ALERT" if alerts else "HEALTHY",
    )


def _event_count(db: Database, account_id: int, event_type: str, window_start: str) -> int:
    row = db.fetchone(
        """SELECT COUNT(*) AS c FROM message_events e
           JOIN messages m ON m.id = e.message_id
           WHERE m.account_id=? AND e.event_type=? AND e.created_at >= ?""",
        (account_id, event_type, window_start),
    )
    return int(row["c"]) if row else 0


def record_event_for_latest_message(
    db: Database, account_id: int, event_type: str, detail: Optional[dict[str, Any]] = None
) -> bool:
    row = db.fetchone(
        "SELECT id FROM messages WHERE account_id=? ORDER BY id DESC LIMIT 1", (account_id,)
    )
    if not row:
        return False
    db.execute(
        "INSERT INTO message_events(message_id, event_type, detail_json, created_at) VALUES (?, ?, ?, ?)",
        (row["id"], event_type, json.dumps(detail or {}, sort_keys=True), utcnow()),
    )
    return True


def run_health_checks(
    db: Database,
    days: int = 14,
    auto_pause: bool = True,
    thresholds: Optional[HealthThresholds] = None,
    provider_checker: Optional[Callable[[dict[str, Any]], tuple[bool, str]]] = None,
    actor: str = "system",
) -> list[HealthReport]:
    accounts = db.fetchall("SELECT * FROM accounts ORDER BY id")
    reports: list[HealthReport] = []
    for account in accounts:
        checker = (lambda acc=dict(account): provider_checker(acc)) if provider_checker else None
        report = compute_health(
            db,
            int(account["id"]),
            days=days,
            thresholds=thresholds,
            provider_check=checker,
        )
        reports.append(report)
        db.execute(
            """INSERT INTO health_snapshots(account_id, metrics_json, status, alerts_json, computed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                account["id"],
                json.dumps(report.metrics, sort_keys=True),
                report.status,
                json.dumps(report.alerts, sort_keys=True),
                utcnow(),
            ),
        )
        if auto_pause and report.alerts and account["status"] == "ACTIVE":
            db.execute(
                "UPDATE accounts SET status='PAUSED', last_error=?, updated_at=? WHERE id=?",
                ("; ".join(report.alerts), utcnow(), account["id"]),
            )
            db.audit(actor, "account.auto_paused", "account", account["id"], {"alerts": report.alerts})
    return reports
