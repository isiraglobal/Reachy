"""Pillar 1: Volume & Infrastructure Capacity Planner.

Implements the exact math from the architecture blueprint:
- ~10 emails / inbox / day (anti-burn limit)
- 3 inboxes / domain
- 100k emails/month ≈ 450 inboxes (150 domains)
- 1M emails/month ≈ 4,500 inboxes (1,500 domains)
- ESP Matcher & Provider Split: Google (5-10% reply), Outlook (0.5-1% reply), Other (1-3% reply)
- 6.5x higher reply rate matching sending provider to target receiving provider
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any, List
import dns.resolver
import re


@dataclass
class VolumePlan:
    target_monthly_volume: int
    working_days_per_month: int = 22
    emails_per_inbox_per_day: int = 10
    inboxes_per_domain: int = 3

    # Computed fields
    daily_volume: int = 0
    inboxes_needed: int = 0
    domains_needed: int = 0
    infra_tier: str = ""

    def __post_init__(self):
        self.daily_volume = int(self.target_monthly_volume / self.working_days_per_month)
        # inboxes needed = daily_volume / 10
        self.inboxes_needed = max(1, int(self.daily_volume / self.emails_per_inbox_per_day))
        self.domains_needed = max(1, int((self.inboxes_needed + self.inboxes_per_domain - 1) / self.inboxes_per_domain))
        
        if self.inboxes_needed <= 50:
            self.infra_tier = "Tier 1: Boutique / Freelance (Manual tracking possible)"
        elif self.inboxes_needed <= 450:
            self.infra_tier = "Tier 2: Growth / 100k Monthly (Trackable with light dashboard)"
        else:
            self.infra_tier = "Tier 3: Enterprise Scale / 1M+ Monthly (Requires automated domain pool infrastructure)"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ESPProviderDetector:
    """Detects target receiving ESP via DNS MX records.

    Rule from blueprint: "For enterprise TAMs, match the sending provider to the receiving one.
    6.5X higher reply rate sending Google-to-Google vs Google-to-Microsoft."
    """

    GOOGLE_MX_PATTERNS = [r"google\.com", r"googlemail\.com", r"aspmx\.l\.google\.com"]
    MICROSOFT_MX_PATTERNS = [r"outlook\.com", r"protection\.outlook\.com", r"mail\.protection\.outlook\.com", r"office365\.com"]

    @classmethod
    def detect_esp_from_domain(cls, domain: str) -> Dict[str, Any]:
        """Looks up MX records for target domain and classifies target ESP."""
        domain = domain.lower().strip()
        mx_records = []
        try:
            answers = dns.resolver.resolve(domain, "MX", lifetime=3.0)
            mx_records = [r.exchange.to_text().rstrip(".") for r in answers]
        except Exception:
            # Fallback if domain DNS lookup fails or offline
            mx_records = []

        combined = " ".join(mx_records).lower()
        esp = "Other"
        recommended_sender_esp = "Google"

        for pat in cls.GOOGLE_MX_PATTERNS:
            if re.search(pat, combined):
                esp = "Google Workspace"
                recommended_sender_esp = "Google Workspace"
                expected_reply_rate = "5-10%"
                break
        else:
            for pat in cls.MICROSOFT_MX_PATTERNS:
                if re.search(pat, combined):
                    esp = "Microsoft 365 / Outlook"
                    recommended_sender_esp = "Microsoft 365"
                    expected_reply_rate = "0.5-1% (Without ESP matching) -> Boosts up to 6.5X with M365 sender"
                    break
            else:
                esp = "Other (Zoho, self-hosted, etc.)"
                recommended_sender_esp = "Other"
                expected_reply_rate = "1-3%"

        return {
            "domain": domain,
            "target_esp": esp,
            "recommended_sending_esp": recommended_sender_esp,
            "mx_records": mx_records[:3],
            "esp_matching_advantage": "6.5X Reply Multiplier applied" if esp in ["Google Workspace", "Microsoft 365 / Outlook"] else "Standard",
        }
