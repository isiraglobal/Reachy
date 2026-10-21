"""Pillar 5: Results, Speed-to-Lead & Prospect-to-Lead (PTL) Engine.

Implements the blueprint specifications:
- RUN THE 500 + THE 100K:
  * 5% of 500 = 25 replies (hyper-tailored boutique list)
  * 1% of 100,000 = 1,000 replies (broad universal scale)
  * "Do both: tiny perfect lists + broad universal messaging at scale."
- TRACK PTL:
  * PTL = prospects-to-lead
  * "Under 500 = extremely solid."
- SPEED TO LEAD:
  * Positive reply -> meeting booked:
    ~80% if answered in < 5 minutes
    ~20% if slow (> 30 mins)
- CLIENT EARLY WARNING:
  * Compare every client/campaign against averages to catch problems before they complain.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional


@dataclass
class CampaignResultsModel:
    campaign_name: str
    campaign_tier: str  # "500_TINY_PERFECT" or "100K_BROAD_SCALE"
    prospects_contacted: int
    positive_replies: int
    meetings_booked: int
    replies_answered_under_5min: int = 0
    replies_answered_slow: int = 0

    # Computed metrics
    ptl: float = 0.0  # Prospects-To-Lead
    reply_rate_pct: float = 0.0
    conversion_to_meeting_pct: float = 0.0
    speed_to_lead_advantage: str = ""

    def calculate_metrics(self) -> Dict[str, Any]:
        # PTL = prospects / meetings
        self.ptl = (self.prospects_contacted / max(1, self.meetings_booked))
        self.reply_rate_pct = (self.positive_replies / max(1, self.prospects_contacted)) * 100
        self.conversion_to_meeting_pct = (self.meetings_booked / max(1, self.positive_replies)) * 100

        # Speed to lead analysis
        # Blueprint: 80% if < 5m, 20% if slow
        fast_meetings = self.replies_answered_under_5min * 0.80
        slow_meetings = self.replies_answered_slow * 0.20
        projected_potential = int(fast_meetings + slow_meetings)

        # Health benchmark: PTL under 500 is extremely solid
        ptl_status = "EXTREMELY_SOLID (PTL < 500)" if self.ptl <= 500 else "NEEDS_OPTIMIZATION (PTL > 500)"

        return {
            "campaign_name": self.campaign_name,
            "campaign_tier": self.campaign_tier,
            "prospects_contacted": self.prospects_contacted,
            "positive_replies": self.positive_replies,
            "meetings_booked": self.meetings_booked,
            "reply_rate": f"{self.reply_rate_pct:.2f}%",
            "ptl_score": f"{self.ptl:.1f}",
            "ptl_assessment": ptl_status,
            "speed_to_lead": {
                "fast_responses_under_5m": self.replies_answered_under_5min,
                "slow_responses": self.replies_answered_slow,
                "insight": "Replies responded to within 5 minutes convert at ~80% vs ~20% for slow responses."
            }
        }


class DualStrategyCalculator:
    """Calculates dual pipeline outcome: Run the 500 (hyper-personalized) + Run the 100k (broad scale)."""

    @classmethod
    def simulate_dual_funnel(cls) -> Dict[str, Any]:
        # 5% of 500 = 25 replies
        tier_500 = {
            "strategy": "Tiny Perfect List (500 ICPs)",
            "volume": 500,
            "reply_rate": "5.0%",
            "replies": 25,
            "speed_under_5m_rate": "80%",
            "meetings": int(25 * 0.80),  # 20 meetings
            "ptl": 500 / 20  # 25 PTL (Super solid)
        }

        # 1% of 100,000 = 1,000 replies
        tier_100k = {
            "strategy": "Broad Universal Messaging Scale (100k)",
            "volume": 100000,
            "reply_rate": "1.0%",
            "replies": 1000,
            "speed_under_5m_rate": "80%",
            "meetings": int(1000 * 0.50),  # 500 meetings
            "ptl": 100000 / 500  # 200 PTL (Solid)
        }

        total_meetings = tier_500["meetings"] + tier_100k["meetings"]

        return {
            "principle": "Do both: tiny perfect lists + broad universal messaging at scale.",
            "tier_500_boutique": tier_500,
            "tier_100k_scale": tier_100k,
            "combined_meetings_generated": total_meetings,
            "ptl_benchmark": "Target under 500 for high capital efficiency."
        }
