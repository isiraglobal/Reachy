"""Gmail warmup curves, safe daily sending limits, and intelligent human-paced batching.

Built by ISIRA Automations for Reachy.
Ensures sending accounts ramp volume safely to protect domain and IP reputation,
distributing messages evenly across business hours with humanized jitter to prevent
spam filter burst heuristics.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

from .db import Database, utcnow
from .models import parse_iso


@dataclass
class WarmupStage:
    min_days: int
    max_days: int
    name: str
    daily_limit: int


# Standard conservative Gmail cold outreach warmup schedule (industry standard)
GMAIL_WARMUP_STAGES = [
    WarmupStage(0, 3, "Initial Seeding", 5),
    WarmupStage(4, 7, "Gradual Ramp 1", 10),
    WarmupStage(8, 14, "Gradual Ramp 2", 18),
    WarmupStage(15, 21, "Midline Ramp", 28),
    WarmupStage(22, 30, "Matured Scale", 40),
    WarmupStage(31, 9999, "Fully Warmed", 50),
]

MAX_SAFE_GMAIL_COLD_LIMIT = 50


@dataclass
class WarmupStatus:
    account_id: int
    email: str
    warmup_enabled: bool
    warmup_started_at: str
    age_days: int
    stage_name: str
    warmup_daily_limit: int
    account_configured_limit: int
    effective_daily_limit: int
    sends_today: int
    remaining_today: int
    days_to_full_warmup: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "email": self.email,
            "warmup_enabled": self.warmup_enabled,
            "warmup_started_at": self.warmup_started_at,
            "age_days": self.age_days,
            "stage_name": self.stage_name,
            "warmup_daily_limit": self.warmup_daily_limit,
            "account_configured_limit": self.account_configured_limit,
            "effective_daily_limit": self.effective_daily_limit,
            "sends_today": self.sends_today,
            "remaining_today": self.remaining_today,
            "days_to_full_warmup": self.days_to_full_warmup,
        }


def get_account_warmup_status(
    db: Database,
    account_id: int,
    now: Optional[datetime] = None,
) -> WarmupStatus:
    """Computes an account's warmup age, stage, and safe daily limit."""
    account = db.fetchone("SELECT * FROM accounts WHERE id = ?", (account_id,))
    if not account:
        raise KeyError(f"account {account_id} not found")

    now = now or datetime.now(timezone.utc)
    today_str = now.date().isoformat()

    warmup_enabled = bool(account["warmup_enabled"] if "warmup_enabled" in account.keys() else 1)
    started_str = (
        account["warmup_started_at"]
        if "warmup_started_at" in account.keys() and account["warmup_started_at"]
        else (account["authorized_at"] or account["created_at"])
    )

    try:
        started_dt = parse_iso(started_str)
    except Exception:
        started_dt = now

    age_days = max(0, (now.date() - started_dt.date()).days)
    sends_today = int(account["sends_today"]) if account["sends_today_date"] == today_str else 0
    configured_limit = int(account["daily_limit"])

    if not warmup_enabled:
        return WarmupStatus(
            account_id=account_id,
            email=account["email"],
            warmup_enabled=False,
            warmup_started_at=started_dt.isoformat(),
            age_days=age_days,
            stage_name="Warmup Disabled (Manual Limit)",
            warmup_daily_limit=configured_limit,
            account_configured_limit=configured_limit,
            effective_daily_limit=configured_limit,
            sends_today=sends_today,
            remaining_today=max(0, configured_limit - sends_today),
            days_to_full_warmup=0,
        )

    # Determine stage
    active_stage = GMAIL_WARMUP_STAGES[-1]
    for stage in GMAIL_WARMUP_STAGES:
        if stage.min_days <= age_days <= stage.max_days:
            active_stage = stage
            break

    # Cap by configured limit and safe ceiling
    warmup_limit = active_stage.daily_limit
    effective_limit = min(configured_limit, warmup_limit)
    days_to_full = max(0, 31 - age_days)

    return WarmupStatus(
        account_id=account_id,
        email=account["email"],
        warmup_enabled=True,
        warmup_started_at=started_dt.isoformat(),
        age_days=age_days,
        stage_name=active_stage.name,
        warmup_daily_limit=warmup_limit,
        account_configured_limit=configured_limit,
        effective_daily_limit=effective_limit,
        sends_today=sends_today,
        remaining_today=max(0, effective_limit - sends_today),
        days_to_full_warmup=days_to_full,
    )


def plan_warmup_batches(
    db: Database,
    campaign_id: int,
    start_date: Optional[date] = None,
    skip_weekends: bool = True,
    business_start_hour: int = 9,
    business_end_hour: int = 17,
    seed: int = 42,
) -> dict[str, Any]:
    """Divides campaign leads into safe daily warmup batches with human-like time jitter.

    Ensures no batch exceeds the account's safe daily warmup limit and distributes
    individual sends across working business hours.
    """
    rng = random.Random(seed)
    campaign = db.fetchone("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    if not campaign:
        raise KeyError(f"campaign {campaign_id} not found")

    account_id = campaign["account_id"]
    if not account_id:
        raise ValueError("campaign must have an attached account to plan warmup batches")

    # Fetch initial step 1 messages that need scheduling
    step1_messages = db.fetchall(
        """SELECT * FROM messages
           WHERE campaign_id = ? AND step_number = 1 AND state IN ('PLANNED', 'QUEUED')
           ORDER BY id""",
        (campaign_id,),
    )
    if not step1_messages:
        raise ValueError("no unfulfilled step 1 messages found to batch")

    start_date = start_date or datetime.now(timezone.utc).date()
    current_date = start_date
    status = get_account_warmup_status(db, account_id)

    # Calculate batch dates and slots
    scheduled_count = 0
    batches: list[dict[str, Any]] = []
    msg_index = 0
    total_messages = len(step1_messages)

    while msg_index < total_messages:
        if skip_weekends and current_date.weekday() in (5, 6):  # Saturday or Sunday
            current_date += timedelta(days=1)
            continue

        # Calculate limit for this date based on progressive warmup
        simulated_age = status.age_days + (current_date - start_date).days
        day_limit = _limit_for_age(simulated_age, status.account_configured_limit, status.warmup_enabled)

        # How many messages to schedule on this day
        day_batch_size = min(day_limit, total_messages - msg_index)
        day_messages = step1_messages[msg_index : msg_index + day_batch_size]

        # Distribute messages across business hours with human jitter
        # Total business window seconds
        window_seconds = (business_end_hour - business_start_hour) * 3600
        step_gap = window_seconds / max(1, day_batch_size + 1)

        batch_details = []
        for i, msg in enumerate(day_messages):
            # Target second in day
            target_second = int((i + 1) * step_gap)
            # Add humanized jitter: +/- 20% of step_gap
            jitter = rng.randint(-int(step_gap * 0.20), int(step_gap * 0.20))
            scheduled_second = max(60, min(window_seconds - 60, target_second + jitter))

            slot_time = time(
                hour=business_start_hour + (scheduled_second // 3600),
                minute=(scheduled_second % 3600) // 60,
                second=scheduled_second % 60,
            )
            scheduled_dt = datetime.combine(current_date, slot_time, tzinfo=timezone.utc)
            scheduled_iso = scheduled_dt.isoformat()

            # Update step 1 message scheduled_at
            db.execute(
                "UPDATE messages SET scheduled_at = ?, updated_at = ? WHERE id = ?",
                (scheduled_iso, utcnow(), msg["id"]),
            )

            # Update subsequent follow-up steps for this contact
            followups = db.fetchall(
                """SELECT m.id, cs.delay_days
                   FROM messages m
                   JOIN campaign_steps cs ON cs.campaign_id = m.campaign_id AND cs.step_number = m.step_number
                   WHERE m.campaign_id = ? AND m.contact_id = ? AND m.step_number > 1
                   ORDER BY m.step_number""",
                (campaign_id, msg["contact_id"]),
            )

            cumulative_dt = scheduled_dt
            for f in followups:
                delay = int(f["delay_days"])
                cumulative_dt = cumulative_dt + timedelta(days=delay)
                # If followup lands on weekend, shift to Monday
                if skip_weekends and cumulative_dt.weekday() in (5, 6):
                    days_ahead = 7 - cumulative_dt.weekday()
                    cumulative_dt = cumulative_dt + timedelta(days=days_ahead)
                # Add slight random minute jitter (+/- 15 mins)
                f_jitter = rng.randint(-900, 900)
                f_scheduled = cumulative_dt + timedelta(seconds=f_jitter)
                db.execute(
                    "UPDATE messages SET scheduled_at = ?, updated_at = ? WHERE id = ?",
                    (f_scheduled.isoformat(), utcnow(), f["id"]),
                )

            batch_details.append({
                "message_id": msg["id"],
                "to_email": msg["to_email"],
                "scheduled_at": scheduled_iso,
            })
            scheduled_count += 1

        batches.append({
            "date": current_date.isoformat(),
            "weekday": current_date.strftime("%A"),
            "daily_limit": day_limit,
            "scheduled_count": len(day_messages),
            "window": f"{business_start_hour:02d}:00 - {business_end_hour:02d}:00 UTC",
        })

        msg_index += day_batch_size
        current_date += timedelta(days=1)

    db.audit(
        "system",
        "campaign.batches_planned",
        "campaign",
        campaign_id,
        {"batches_count": len(batches), "scheduled_messages": scheduled_count},
    )

    return {
        "campaign_id": campaign_id,
        "account_id": account_id,
        "total_messages_batched": scheduled_count,
        "days_span": len(batches),
        "batches": batches,
    }


def _limit_for_age(age_days: int, configured_limit: int, warmup_enabled: bool) -> int:
    if not warmup_enabled:
        return configured_limit
    for stage in GMAIL_WARMUP_STAGES:
        if stage.min_days <= age_days <= stage.max_days:
            return min(configured_limit, stage.daily_limit)
    return min(configured_limit, MAX_SAFE_GMAIL_COLD_LIMIT)
