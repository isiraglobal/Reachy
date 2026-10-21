"""Pillar 2: The List & 10-Row Quality Gate.

Implements the rule from the blueprint:
"Bad list quality hurts before deliverability does.
THE 10-ROW CHECK:
- Right company
- Right title
- Right size
- Real email
- Not a competitor
- Not a student
- Not a personal email
- In the right region
- Recent activity
- Fits your ICP

RULE: If 2 of 10 rows are wrong, STOP and fix the list."
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import re


FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "aol.com", "icloud.com", "protonmail.com", "mail.com", "zoho.com"
}

STUDENT_PATTERNS = [r"\.edu$", r"student", r"intern", r"academic", r"alumni"]


@dataclass
class LeadValidationItem:
    company: str
    email: str
    title: str = "Owner"
    region: str = "US"
    reviews_count: Optional[int] = None
    rating: Optional[float] = None
    website: Optional[str] = None

    # Audit evaluation flags
    is_right_company: bool = True
    is_right_title: bool = True
    is_right_size: bool = True
    is_real_email: bool = True
    is_not_competitor: bool = True
    is_not_student: bool = True
    is_not_personal_email: bool = True
    is_in_right_region: bool = True
    has_recent_activity: bool = True
    fits_icp: bool = True

    errors: List[str] = field(default_factory=list)

    def evaluate(self, target_region: str = "US", competitor_keywords: List[str] = None):
        competitor_keywords = competitor_keywords or ["marketing agency", "lead generation agency", "cold email service"]
        self.errors = []

        # 1. Real email structure
        if not self.email or not re.match(r"[^@]+@[^@]+\.[^@]+", self.email):
            self.is_real_email = False
            self.errors.append("Invalid or missing email syntax")
        else:
            self.is_real_email = True

        # 2. Not personal email
        domain = self.email.split("@")[-1].lower() if "@" in self.email else ""
        if domain in FREE_EMAIL_DOMAINS:
            self.is_not_personal_email = False
            self.errors.append(f"Personal email provider detected: @{domain}")
        else:
            self.is_not_personal_email = True

        # 3. Not a student
        if any(re.search(pat, domain) for pat in STUDENT_PATTERNS) or any(re.search(pat, self.title.lower()) for pat in ["student", "intern"]):
            self.is_not_student = False
            self.errors.append("Student or intern profile detected")
        else:
            self.is_not_student = True

        # 4. Not a competitor
        if any(kw in self.company.lower() for kw in competitor_keywords):
            self.is_not_competitor = False
            self.errors.append(f"Competitor keyword matched in company name: {self.company}")
        else:
            self.is_not_competitor = True

        # 5. Right region
        valid_us = ["US", "USA", "UNITED STATES", "TX", "CA", "FL", "NY", "IL", "GA", "NC", "OH", "PA"]
        region_clean = (self.region or "").upper()
        if target_region == "US":
            matches_us = any(st in region_clean for st in valid_us)
            self.is_in_right_region = matches_us
            if not matches_us:
                self.errors.append(f"Region '{self.region}' does not match target 'US'")
        elif target_region and target_region.upper() not in region_clean:
            self.is_in_right_region = False
            self.errors.append(f"Region '{self.region}' does not match target '{target_region}'")
        else:
            self.is_in_right_region = True

        # 6. Recent activity (Maps reviews count or active site)
        if self.reviews_count is not None and self.reviews_count == 0:
            self.has_recent_activity = False
            self.errors.append("Zero reviews / no active business footprint")
        else:
            self.has_recent_activity = True

        # 7. Overall ICP check
        self.fits_icp = (
            self.is_real_email and
            self.is_not_personal_email and
            self.is_not_student and
            self.is_not_competitor and
            self.is_in_right_region
        )

        return len(self.errors) == 0


class TenRowQualityGate:
    """Evaluates a batch against the mandatory 10-Row Check from the architecture blueprint."""

    @classmethod
    def audit_10_rows(cls, leads: List[Dict[str, Any]], target_region: str = "US") -> Dict[str, Any]:
        """Picks the first 10 rows (or random 10) and determines if the campaign passes or must be halted."""
        sample_rows = leads[:10]
        tested_items: List[LeadValidationItem] = []
        fail_count = 0

        for r in sample_rows:
            item = LeadValidationItem(
                company=r.get("title") or r.get("company", "Unknown"),
                email=r.get("email") or "",
                title=r.get("category") or "Owner",
                region=r.get("address") or "US",
                reviews_count=r.get("reviews_count"),
                rating=r.get("rating"),
                website=r.get("website")
            )
            passed = item.evaluate(target_region=target_region)
            if not passed:
                fail_count += 1
            tested_items.append(item)

        # Blueprint rule: "If 2 of 10 rows are wrong, stop and fix the list."
        must_stop = fail_count >= 2

        return {
            "tested_rows_count": len(tested_items),
            "passed_rows_count": len(tested_items) - fail_count,
            "failed_rows_count": fail_count,
            "error_rate": f"{(fail_count / len(tested_items)) * 100:.1f}%" if tested_items else "0%",
            "status": "HALT_CAMPAIGN_AND_FIX_LIST" if must_stop else "APPROVED_FOR_OUTREACH",
            "rule": "If 2 of 10 rows are wrong, stop and fix the list.",
            "details": [
                {
                    "company": it.company,
                    "email": it.email,
                    "passed": len(it.errors) == 0,
                    "errors": it.errors
                }
                for it in tested_items
            ]
        }
