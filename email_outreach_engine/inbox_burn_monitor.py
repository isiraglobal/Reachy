"""Pillar 3: Inbox Burn & Deliverability Lifecycle Engine.

Implements the exact rules from the architecture blueprint:
- BURN IS NORMAL: "Even clean inboxes burn in ~6-9 months."
- THE PLAYBOOK:
  * Monitor daily
  * Alert on bounce / reply dips
  * Swap burned inbox same day
  * Keep per-inbox volume low (10/day)
- DOMAIN RULE:
  * >= 1% reply rate = KEEP
  * < 1% reply rate = REPLACE
- CATCH THE SLOPE:
  * A 2-week downward trend matters before the domain fully fails.
- SHADOW BANNING DETECTION:
  * "0% bounce + 0 replies = likely shadow banned. Rewrite once. If nothing changes, replace within 48 hours."
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import statistics


@dataclass
class InboxHealthRecord:
    inbox_email: str
    domain: str
    age_months: float
    daily_volume: int = 10
    total_sent_14d: int = 140
    daily_reply_rates_14d: List[float] = field(default_factory=list)  # [day1, day2, ..., day14]
    bounce_rate: float = 0.01  # 1%
    replies_count_14d: int = 5

    def evaluate_health(self) -> Dict[str, Any]:
        """Calculates status, slope, and replacement triggers."""
        # Calculate 14-day average reply rate
        avg_reply_rate = (
            statistics.mean(self.daily_reply_rates_14d)
            if self.daily_reply_rates_14d
            else (self.replies_count_14d / max(1, self.total_sent_14d))
        )

        # 1. Shadow Ban Rule: 0% bounce + 0 replies after sending volume
        is_shadow_banned = (self.bounce_rate == 0.0 and self.replies_count_14d == 0 and self.total_sent_14d >= 50)

        # 2. Catch the Slope: Calculate trend over 14 days
        slope = 0.0
        is_negative_slope = False
        if len(self.daily_reply_rates_14d) >= 7:
            first_half = statistics.mean(self.daily_reply_rates_14d[:len(self.daily_reply_rates_14d)//2])
            second_half = statistics.mean(self.daily_reply_rates_14d[len(self.daily_reply_rates_14d)//2:])
            slope = second_half - first_half
            is_negative_slope = slope < -0.005  # Dropping by >0.5% over 2 weeks

        # 3. Domain Rule: >= 1% reply rate = KEEP, < 1% = REPLACE
        domain_status = "KEEP" if avg_reply_rate >= 0.01 else "REPLACE"

        # 4. Burn Lifecycle Warning (6-9 months)
        lifecycle_warning = self.age_months >= 6.0

        # Action Recommendation
        if is_shadow_banned:
            action = "ALERT: Likely shadow banned (0% bounce + 0 replies). Rewrite copy once. If unchanged in 48h, swap inbox immediately."
            status = "CRITICAL_SHADOW_BANNED"
        elif domain_status == "REPLACE":
            action = "ALERT: Reply rate is below 1%. Swap burned inbox same day."
            status = "BURNED_REPLACE_NOW"
        elif is_negative_slope:
            action = "WARNING: 2-week downward slope detected. Prep replacement inbox before complete burn."
            status = "DEGRADING_SLOPE"
        elif lifecycle_warning:
            action = f"NOTICE: Inbox age is {self.age_months:.1f} months. In normal burn window (~6-9 months). Monitor closely."
            status = "AGING_NORMAL"
        else:
            action = "HEALTHY: Operating within standard deliverability thresholds."
            status = "HEALTHY"

        return {
            "inbox": self.inbox_email,
            "domain": self.domain,
            "age_months": self.age_months,
            "avg_reply_rate": f"{avg_reply_rate * 100:.2f}%",
            "domain_rule_status": domain_status,
            "is_shadow_banned": is_shadow_banned,
            "is_downward_slope": is_negative_slope,
            "status": status,
            "action_required": action
        }


class FleetHealthMonitor:
    """Monitors fleet of inboxes and domains across an agency or company."""

    def __init__(self):
        self.records: List[InboxHealthRecord] = []

    def add_inbox(self, record: InboxHealthRecord):
        self.records.append(record)

    def generate_fleet_report(self) -> Dict[str, Any]:
        evaluations = [rec.evaluate_health() for rec in self.records]
        healthy = sum(1 for e in evaluations if e["status"] == "HEALTHY")
        burned_or_replace = sum(1 for e in evaluations if e["domain_rule_status"] == "REPLACE" or e["is_shadow_banned"])
        degrading = sum(1 for e in evaluations if e["status"] == "DEGRADING_SLOPE")

        return {
            "total_inboxes_monitored": len(self.records),
            "healthy_count": healthy,
            "burned_or_replace_count": burned_or_replace,
            "degrading_slope_count": degrading,
            "fleet_health_score": f"{(healthy / max(1, len(self.records))) * 100:.1f}%",
            "evaluations": evaluations
        }
