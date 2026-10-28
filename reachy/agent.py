"""Autonomous outreach agent for final send execution, pre-flight safety gates, and sync loops.

Built by ISIRA Automations for Reachy.
Executes queued campaigns with strict adherence to daily warmup quotas,
health status verification, human pacing intervals, and automatic post-send reply/bounce synchronization.
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .campaign import CampaignWorker, _campaign
from .config import ReachyConfig
from .db import Database, utcnow
from .health import compute_health
from .policy import PolicyEngine
from .providers.base import EmailProvider
from .replies import sync_replies
from .tracking import ensure_tracking_token
from .warmup import get_account_warmup_status


class AutonomousOutreachAgent:
    """Agent that oversees and executes the final campaign send autonomously and safely."""

    def __init__(
        self,
        db: Database,
        config: ReachyConfig,
        provider_factory: Callable[[dict[str, Any]], EmailProvider],
        policy: Optional[PolicyEngine] = None,
        agent_id: str = "reachy_agent",
    ):
        self.db = db
        self.config = config
        self.provider_factory = provider_factory
        self.policy = policy or PolicyEngine(config)
        self.agent_id = agent_id
        self.worker = CampaignWorker(
            db=db,
            config=config,
            provider_factory=provider_factory,
            worker_id=agent_id,
            policy=self.policy,
        )

    def execute_sends(
        self,
        campaign_id: Optional[int] = None,
        max_messages: int = 25,
        pace_seconds: float = 0.0,
        sync_after: bool = True,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Runs the autonomous outreach dispatch loop with safety gates."""
        now = now or datetime.now(timezone.utc)
        now_iso = now.isoformat()

        # 1. Global pause gate
        if self.db.get_setting("global_pause", "0") == "1":
            return {
                "ok": False,
                "status": "HALTED",
                "reason": "Global pause is active",
                "processed": 0,
                "sent": 0,
            }

        # 2. Promote due planned messages to queued
        self.worker._promote_due(now)

        # 3. Filter target accounts / campaigns
        if campaign_id:
            campaign = _campaign(self.db, campaign_id)
            if campaign["status"] != "RUNNING":
                return {
                    "ok": False,
                    "status": "HALTED",
                    "reason": f"Campaign {campaign_id} status is {campaign['status']}, expected RUNNING",
                    "processed": 0,
                    "sent": 0,
                }
            account_id = campaign["account_id"]
        else:
            first_queued = self.db.fetchone(
                """SELECT m.account_id FROM messages m
                   JOIN campaigns c ON c.id = m.campaign_id
                   WHERE m.state = 'QUEUED' AND m.scheduled_at <= ? AND c.status = 'RUNNING'
                   ORDER BY m.scheduled_at LIMIT 1""",
                (now_iso,),
            )
            account_id = first_queued["account_id"] if first_queued else None

        if not account_id:
            return {
                "ok": True,
                "status": "NO_MESSAGES_DUE",
                "reason": "No queued messages currently due for sending",
                "processed": 0,
                "sent": 0,
            }

        # 4. Check account status & health
        account = self.db.fetchone("SELECT * FROM accounts WHERE id = ?", (account_id,))
        if not account or account["status"] not in ("ACTIVE", "PENDING_AUTH"):
            return {
                "ok": False,
                "status": "HALTED",
                "reason": f"Account {account_id} status is {account['status'] if account else 'MISSING'}",
                "processed": 0,
                "sent": 0,
            }

        # Sender Health check: Halt if alert is triggered
        health = compute_health(self.db, account_id, now=now)
        if health.status == "ALERT":
            return {
                "ok": False,
                "status": "HALTED",
                "reason": f"Sender health alert on account {account['email']}: {'; '.join(health.alerts)}",
                "alerts": health.alerts,
                "processed": 0,
                "sent": 0,
            }

        # 5. Check Warmup quota
        warmup = get_account_warmup_status(self.db, account_id, now=now)
        if warmup.remaining_today <= 0:
            return {
                "ok": True,
                "status": "QUOTA_REACHED",
                "reason": f"Daily limit reached for {account['email']} ({warmup.sends_today}/{warmup.effective_daily_limit})",
                "warmup_stage": warmup.stage_name,
                "processed": 0,
                "sent": 0,
            }

        # Determine effective batch limit
        allowed_sends = min(max_messages, warmup.remaining_today)
        summary: dict[str, Any] = {
            "processed": 0,
            "sent": 0,
            "failed": 0,
            "blocked": 0,
            "dry_run": 0,
            "uncertain": 0,
        }

        # 6. Execute message claims and sends
        for i in range(allowed_sends):
            msg = self.worker._claim(now)
            if not msg:
                break

            # Ensure open tracking token
            ensure_tracking_token(self.db, int(msg["id"]))

            outcome = self.worker._process(msg, now)
            summary["processed"] += 1
            summary[outcome] = summary.get(outcome, 0) + 1

            # Natural human pacing delay with slight random jitter if requested
            if pace_seconds > 0 and i < allowed_sends - 1 and outcome in ("sent", "accepted"):
                jitter = random.uniform(-0.15 * pace_seconds, 0.25 * pace_seconds)
                actual_sleep = max(0.1, pace_seconds + jitter)
                time.sleep(actual_sleep)

        # 7. Post-send synchronization of replies and bounces
        sync_result = None
        if sync_after and account["provider"] in ("mock", "smtp", "gmail"):
            try:
                provider = self.provider_factory(dict(account))
                try:
                    sync_result = sync_replies(self.db, account_id, provider, actor=self.agent_id)
                finally:
                    provider.close()
            except Exception as exc:  # noqa: BLE001
                sync_result = {"error": f"Sync failed: {exc}"}

        # Refresh warmup stats after sending
        updated_warmup = get_account_warmup_status(self.db, account_id, now=now)

        self.db.audit(
            self.agent_id,
            "agent.dispatch_completed",
            "account",
            account_id,
            {"sent": summary.get("sent", 0), "processed": summary["processed"]},
        )

        return {
            "ok": True,
            "status": "COMPLETED",
            "account_id": account_id,
            "account_email": account["email"],
            "warmup_stage": updated_warmup.stage_name,
            "sends_today": updated_warmup.sends_today,
            "remaining_today": updated_warmup.remaining_today,
            "results": summary,
            "reply_sync": sync_result,
        }
