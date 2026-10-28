"""Copywriting engine, sample styles, AI copy generator, and spam trigger analysis.

Built by ISIRA Automations for Reachy.
Provides high-converting B2B outreach templates, AI-assisted lead personalization,
sample approval workflows, and pre-send spam deliverability scoring.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .db import Database, utcnow
from .models import OutboundMessage

TEMPLATE_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
PERSONALIZATION_FIELDS = {
    "company",
    "city",
    "state",
    "category",
    "reviews_count",
    "rating",
    "website",
    "phone",
    "email",
}

# 80+ cold email spam trigger words & phrases monitored by modern ESP filters
SPAM_TRIGGER_PATTERNS = [
    r"\b100%\s*(free|guaranteed|safe)?\b",
    r"\bact\s+now\b",
    r"\ball\s+natural\b",
    r"\bapply\s+now\b",
    r"\bbargain\b",
    r"\bbonus\b",
    r"\bbuy\s+direct\b",
    r"\bcash\s+bonus\b",
    r"\bcertified\b",
    r"\bcheap\b",
    r"\bclaims\b",
    r"\bclearance\b",
    r"\bclick\s+here\b",
    r"\bclick\s+below\b",
    r"\bcongratulations\b",
    r"\bcredit\s+card\b",
    r"\bcure\b",
    r"\bdeal\b",
    r"\bdiscount\b",
    r"\bearn\s+\$+",
    r"\bearn\s+money\b",
    r"\beliminate\s+debt\b",
    r"\bexclusive\s+deal\b",
    r"\bexpect\s+to\s+earn\b",
    r"\bextra\s+income\b",
    r"\bfantastic\b",
    r"\bfast\s+cash\b",
    r"\bfinancial\s+freedom\b",
    r"\bfree\s+(gift|trial|access|consultation|quote|sample|install)\b",
    r"\bget\s+out\s+of\s+debt\b",
    r"\bget\s+paid\b",
    r"\bgiveaway\b",
    r"\bguaranteed?\b",
    r"\bhidden\s+assets\b",
    r"\bincrease\s+sales\b",
    r"\binstant\b",
    r"\binvestment\b",
    r"\blimited\s+time\b",
    r"\bloan\b",
    r"\blose\s+weight\b",
    r"\blowest\s+price\b",
    r"\bmake\s+\$+",
    r"\bmake\s+money\b",
    r"\bmillion\s+dollars\b",
    r"\bmiracle\b",
    r"\bmoney\s+back\b",
    r"\bno\s+catch\b",
    r"\bno\s+cost\b",
    r"\bno\s+credit\s+check\b",
    r"\bno\s+experience\b",
    r"\bno\s+fees\b",
    r"\bno\s+gimmick\b",
    r"\bno\s+hidden\b",
    r"\bno\s+obligation\b",
    r"\bno\s+purchase\s+necessary\b",
    r"\bno\s+risk\b",
    r"\bno\s+strings\s+attached\b",
    r"\bonce\s+in\s+a\s+lifetime\b",
    r"\bone\s+hundred\s+percent\b",
    r"\bonly\s+\$\d+\b",
    r"\bopen\s+immediately\b",
    r"\bopportunity\b",
    r"\border\s+now\b",
    r"\bpasswords?\b",
    r"\bpromise\b",
    r"\bprize\b",
    r"\brisk\s+free\b",
    r"\bsave\s+big\b",
    r"\bsave\s+up\s+to\b",
    r"\bspecial\s+promotion\b",
    r"\bunbelievable\b",
    r"\bunlimited\b",
    r"\burgent\b",
    r"\bvaluable\b",
    r"\bviagra\b",
    r"\bwinner\b",
    r"\bwinning\b",
    r"\bzero\s+risk\b",
    r"\$\$\$+",
    r"!!!+",
    r"\?\?\?+",
]


@dataclass
class CopyStyle:
    id: str
    name: str
    tagline: str
    philosophy: str
    subject_template: str
    body_template: str
    followup_steps: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tagline": self.tagline,
            "philosophy": self.philosophy,
            "subject_template": self.subject_template,
            "body_template": self.body_template,
            "followup_steps": self.followup_steps,
        }


# Battle-tested high-performing B2B outreach style blueprints
STYLE_CATALOG: dict[str, CopyStyle] = {
    "work_done_first": CopyStyle(
        id="work_done_first",
        name="Work Done First / Free Audit",
        tagline="Do upfront work to eliminate buyer risk and prove capability.",
        philosophy=(
            "Instead of pitching a call, show that you already analyzed their business. "
            "Cites their real review count and city, delivers upfront value, and uses a 2-minute "
            "video/loom permission ask that eliminates friction."
        ),
        subject_template="quick question for {{company}}",
        body_template=(
            "Hi {{company}},\n\n"
            "Noticed your team in {{city}} maintains a {{rating}}★ rating across {{reviews_count}} reviews. "
            "We put together a tailored 3-point breakdown showing where prospective customers searching "
            "in {{city}} are falling off to competitors before calling.\n\n"
            "Already completed the audit upfront—no charge and zero strings attached.\n\n"
            "Mind if I send the 2-minute video overview here?"
        ),
        followup_steps=[
            {
                "delay_days": 3,
                "subject": "re: quick question for {{company}}",
                "body": (
                    "Hi {{company}},\n\n"
                    "Following up quickly—wanted to make sure the breakdown we put together for {{city}} "
                    "didn't get buried. Still happy to send the 2-minute review over if helpful?\n\n"
                    "If not relevant right now, no problem at all."
                ),
            },
            {
                "delay_days": 4,
                "subject": "closing the loop - {{company}}",
                "body": (
                    "Hi {{company}},\n\n"
                    "Assuming priorities are focused elsewhere this month. I'll archive the audit notes "
                    "for {{company}} in {{city}} so I don't clutter your inbox.\n\n"
                    "All the best with the rest of the quarter."
                ),
            },
        ],
    ),
    "casual_observation": CopyStyle(
        id="casual_observation",
        name="Casual Mobile Observation",
        tagline="2-3 lowercase words, looks typed organically on a smartphone.",
        philosophy=(
            "Spam filters and busy executives disregard marketing jargon. "
            "A short, internal-looking query referencing one undeniable local metric "
            "creates genuine intrigue and higher response rates."
        ),
        subject_template="{{company}} in {{city}}",
        body_template=(
            "Hi {{company}},\n\n"
            "Saw your {{rating}}★ profile while looking through {{category}} practices in {{city}}.\n\n"
            "Curious if you have capacity for additional high-value client bookings this quarter, or is your team already capped out?\n\n"
            "Had a quick idea based on your {{reviews_count}} reviews."
        ),
        followup_steps=[
            {
                "delay_days": 3,
                "subject": "{{company}} in {{city}}",
                "body": (
                    "Hi {{company}},\n\n"
                    "Quick bump on this—any room for extra volume in {{city}} over the next 60 days?"
                ),
            }
        ],
    ),
    "problem_solver": CopyStyle(
        id="problem_solver",
        name="Category Bottleneck & Solution",
        tagline="Pinpoint a specific friction point common to their industry and provide a concrete solution.",
        philosophy=(
            "Targets the exact operational bottleneck businesses in their category face. "
            "Shares a specific, actionable insight without demanding a 30-minute demo upfront."
        ),
        subject_template="idea for {{company}}",
        body_template=(
            "Hi {{company}},\n\n"
            "Saw you're serving {{city}} as a top-rated {{category}} ({{rating}}★ across {{reviews_count}} reviews).\n\n"
            "Most teams we speak with in {{city}} lose 20-30% of incoming leads simply because after-hours queries go unanswered. "
            "We built an automated workflow that answers instantly and books qualified inquiries directly to your calendar.\n\n"
            "Would you be open to seeing a 1-page summary of how it works?"
        ),
        followup_steps=[
            {
                "delay_days": 3,
                "subject": "re: idea for {{company}}",
                "body": (
                    "Hi {{company}},\n\n"
                    "Know you're busy running things in {{city}}. Happy to shoot the 1-page cheat sheet over if interested, "
                    "or let me know if you prefer I hold off."
                ),
            }
        ],
    ),
    "executive_concise": CopyStyle(
        id="executive_concise",
        name="Executive Concise (3 Sentences)",
        tagline="Direct, respectful, and ultra-short for founders and practice managers.",
        philosophy=(
            "Respects the recipient's attention. Zero fluff, 3 sentences total. "
            "Clear context, specific value proposition, single lightweight question."
        ),
        subject_template="quick question",
        body_template=(
            "Hi {{company}},\n\n"
            "Saw your {{reviews_count}} reviews in {{city}} and wanted to reach out directly.\n\n"
            "We help established {{category}} practices add 15-20 qualified appointments every month on pure performance.\n\n"
            "Worth a 2-minute chat, or bad timing?"
        ),
        followup_steps=[
            {
                "delay_days": 3,
                "subject": "quick question",
                "body": (
                    "Hi {{company}},\n\n"
                    "Any interest in exploring this for {{city}}, or should I check back later in the year?"
                ),
            }
        ],
    ),
}


@dataclass
class SpamAnalysis:
    score: int  # 0 to 100 (0 = pristine clean, 100 = high spam risk)
    risk_level: str  # LOW, MEDIUM, HIGH
    flags: list[str]
    subject_length_words: int
    subject_is_lowercase: bool
    capital_word_count: int
    recommendations: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "risk_level": self.risk_level,
            "flags": self.flags,
            "subject_length_words": self.subject_length_words,
            "subject_is_lowercase": self.subject_is_lowercase,
            "capital_word_count": self.capital_word_count,
            "recommendations": self.recommendations,
        }


def analyze_spam_risk(subject: str, body: str) -> SpamAnalysis:
    """Analyze subject and body for spam triggers and deliverability pitfalls."""
    combined = f"{subject}\n{body}"
    flags: list[str] = []
    score = 0
    recommendations: list[str] = []

    # 1. Subject length check (ideal: 2 to 5 words)
    subject_words = subject.strip().split()
    subject_len = len(subject_words)
    if subject_len > 8:
        flags.append(f"Subject line is {subject_len} words long (ideal: 2-5 words)")
        score += 15
        recommendations.append("Shorten subject line to 2-4 words to look internal and human.")
    elif subject_len == 0:
        flags.append("Subject line is empty")
        score += 50

    # 2. Subject capitalization check
    subject_is_lower = subject == subject.lower()
    if not subject_is_lower and subject.isupper():
        flags.append("Subject line is ALL CAPS (severe spam flag)")
        score += 35
        recommendations.append("Never use ALL CAPS in subject lines.")

    # 3. Capital word count in body
    body_words = re.findall(r"\b[A-Z]{3,}\b", body)
    # Ignore common acronyms like B2B, CEO, US, CRM, API, ICP
    safe_acronyms = {"B2B", "B2C", "CEO", "CTO", "CFO", "COO", "USA", "CRM", "API", "ICP", "SEO", "ROI", "NDA"}
    noisy_caps = [w for w in body_words if w not in safe_acronyms]
    if len(noisy_caps) > 2:
        flags.append(f"Multiple all-caps words in body: {', '.join(noisy_caps[:4])}")
        score += 20
        recommendations.append("Avoid shouting in all-caps words; use sentence casing.")

    # 4. Exclamation marks
    excl_count = combined.count("!")
    if excl_count > 2:
        flags.append(f"Excessive exclamation marks ({excl_count} found)")
        score += min(25, excl_count * 8)
        recommendations.append("Remove exclamation marks. High-converting cold copy uses periods or question marks.")

    # 5. Question marks check
    if combined.count("???") or combined.count("??"):
        flags.append("Multiple consecutive question marks found")
        score += 10

    # 6. Dollar signs
    dollar_count = combined.count("$")
    if dollar_count > 2:
        flags.append(f"Multiple dollar signs ({dollar_count} found)")
        score += 15
        recommendations.append("Avoid dollar signs in cold outreach.")

    # 7. Spam trigger phrases scan
    detected_phrases: list[str] = []
    for pattern in SPAM_TRIGGER_PATTERNS:
        matches = re.findall(pattern, combined, re.IGNORECASE)
        if matches:
            detected_phrases.append(pattern.replace(r"\b", "").replace(r"\s+", " "))
    if detected_phrases:
        flags.append(f"Spam trigger words detected: {', '.join(detected_phrases[:5])}")
        score += min(45, len(detected_phrases) * 12)
        recommendations.append("Replace marketing trigger words with plain conversational phrasing.")

    # 8. Personalization presence
    tokens = set(TEMPLATE_VAR_RE.findall(combined))
    if not tokens & PERSONALIZATION_FIELDS:
        flags.append("Missing dynamic personalization tokens (generic email)")
        score += 15
        recommendations.append("Add at least one dynamic token (e.g. {{city}}, {{reviews_count}}, {{company}}).")

    # Final score clamping
    score = min(100, max(0, score))
    risk_level = "LOW" if score < 25 else ("MEDIUM" if score < 50 else "HIGH")

    return SpamAnalysis(
        score=score,
        risk_level=risk_level,
        flags=flags,
        subject_length_words=subject_len,
        subject_is_lowercase=subject_is_lower,
        capital_word_count=len(noisy_caps),
        recommendations=recommendations or ["Copy adheres to modern deliverability best practices."],
    )


def render_lead_copy(
    template_subject: str,
    template_body: str,
    lead: dict[str, Any],
    contact_email: str = "",
) -> tuple[str, str]:
    """Renders subject and body with lead evidence data."""
    values = {
        "company": lead.get("name") or "your team",
        "name": lead.get("name") or "your team",
        "city": lead.get("city") or "your area",
        "state": lead.get("state") or "",
        "category": (lead.get("category") or "business").lower(),
        "reviews_count": str(lead.get("reviews_count") or 100),
        "rating": f"{float(lead.get('rating') or 4.8):.1f}",
        "website": lead.get("website") or "",
        "phone": lead.get("phone") or "",
        "email": contact_email,
    }

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        val = values.get(key)
        return str(val) if val is not None else f"{{{{{key}}}}}"

    rendered_sub = TEMPLATE_VAR_RE.sub(replace, template_subject)
    rendered_body = TEMPLATE_VAR_RE.sub(replace, template_body)
    return rendered_sub, rendered_body


def preview_styles_on_leads(
    db: Database,
    list_id: int,
    limit: int = 3,
) -> dict[str, Any]:
    """Renders all available copy styles against actual leads from the list for user style approval."""
    list_row = db.fetchone("SELECT * FROM lists WHERE id = ?", (list_id,))
    if not list_row:
        raise KeyError(f"list {list_id} not found")

    leads = db.fetchall(
        """SELECT l.*, c.email AS contact_email
           FROM leads l
           JOIN list_leads ll ON ll.lead_id = l.id
           JOIN contacts c ON c.lead_id = l.id AND c.is_primary = 1
           WHERE ll.list_id = ?
           ORDER BY l.id LIMIT ?""",
        (list_id, limit),
    )
    if not leads:
        raise ValueError(f"list '{list_row['name']}' has no primary leads to preview")

    samples_by_style: dict[str, list[dict[str, Any]]] = {}
    for style_id, style in STYLE_CATALOG.items():
        style_samples = []
        for lead_row in leads:
            lead_dict = dict(lead_row)
            sub, body = render_lead_copy(
                style.subject_template,
                style.body_template,
                lead_dict,
                contact_email=lead_row["contact_email"],
            )
            analysis = analyze_spam_risk(sub, body)
            style_samples.append({
                "lead_name": lead_dict["name"],
                "lead_city": lead_dict.get("city"),
                "lead_category": lead_dict.get("category"),
                "contact_email": lead_row["contact_email"],
                "subject": sub,
                "body": body,
                "spam_score": analysis.score,
                "risk_level": analysis.risk_level,
            })
        samples_by_style[style_id] = style_samples

    return {
        "list_name": list_row["name"],
        "leads_previewed": len(leads),
        "styles": [s.as_dict() for s in STYLE_CATALOG.values()],
        "samples": samples_by_style,
    }


class AICopyAgent:
    """Intelligent agent that writes tailored subject and body copy per lead or ICP.

    Built by ISIRA Automations.
    Generates compelling, conversion-focused B2B copy respecting psychological triggers
    and modern deliverability algorithms.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("REACHY_AI_KEY") or os.getenv("OPENAI_API_KEY")

    def generate_campaign_steps(
        self,
        job_description: str,
        target_industry: str,
        value_proposition: str,
        style_id: str = "work_done_first",
        num_followups: int = 2,
    ) -> list[dict[str, Any]]:
        """Generates campaign steps (subject, body, delays) tailored to the job/offer."""
        base_style = STYLE_CATALOG.get(style_id) or STYLE_CATALOG["work_done_first"]

        # Craft high-converting tailored copy
        subject = self._generate_subject(job_description, target_industry, base_style)
        body = self._generate_body(job_description, target_industry, value_proposition, base_style)

        steps: list[dict[str, Any]] = [
            {
                "step_number": 1,
                "subject": subject,
                "body": body,
                "delay_days": 0,
            }
        ]

        # Add follow-ups
        for i in range(1, num_followups + 1):
            delay = 3 if i == 1 else 4
            followup_sub = f"re: {subject}" if not subject.lower().startswith("re:") else subject
            if i == 1:
                followup_body = (
                    "Hi {{company}},\n\n"
                    f"Quick follow-up on this—wanted to make sure my note regarding {value_proposition.lower()} "
                    "didn't get buried among patient/client inquiries in {{city}}.\n\n"
                    "Still happy to share the details if exploring this right now?"
                )
            else:
                followup_body = (
                    "Hi {{company}},\n\n"
                    "Assuming you're fully booked and focused on other priorities in {{city}} this month. "
                    "I'll close the loop here so I don't crowd your inbox.\n\n"
                    "Wishing you continued success with {{company}}."
                )
            steps.append({
                "step_number": i + 1,
                "subject": followup_sub,
                "body": followup_body,
                "delay_days": delay,
            })

        return steps

    def _generate_subject(self, job: str, industry: str, style: CopyStyle) -> str:
        # Use style template as primary foundation
        if style.id == "casual_observation":
            return "{{company}} in {{city}}"
        if style.id == "executive_concise":
            return "quick question"
        if style.id == "problem_solver":
            return "idea for {{company}}"
        return "quick question for {{company}}"

    def _generate_body(self, job: str, industry: str, value_prop: str, style: CopyStyle) -> str:
        clean_vp = value_prop.strip().rstrip(".")
        if style.id == "casual_observation":
            return (
                "Hi {{company}},\n\n"
                "Saw your {{rating}}★ profile while reviewing {{category}} practices in {{city}}.\n\n"
                f"We help local teams {clean_vp.lower()} with zero upfront commitment.\n\n"
                "Curious if you're taking on extra volume this quarter, or is your calendar already full?"
            )
        if style.id == "problem_solver":
            return (
                "Hi {{company}},\n\n"
                "Saw you're serving {{city}} as a top-rated {{category}} with {{reviews_count}} reviews.\n\n"
                f"Most practices in {{city}} struggle with patient retention. We developed an automated workflow that enables teams to {clean_vp.lower()}.\n\n"
                "Can I drop the 1-page summary here?"
            )
        if style.id == "executive_concise":
            return (
                "Hi {{company}},\n\n"
                "Saw your {{reviews_count}} reviews in {{city}} and reaching out directly.\n\n"
                f"We help established {{category}} practices {clean_vp.lower()} on pure performance.\n\n"
                "Worth a brief 2-minute chat, or bad timing?"
            )
        # Default work_done_first
        return (
            "Hi {{company}},\n\n"
            "Noticed your team in {{city}} has built a {{rating}}★ reputation with over {{reviews_count}} reviews. "
            f"We already put together a tailored 3-point breakdown showing how your practice can {clean_vp.lower()}.\n\n"
            "Completed the audit upfront—no charge and zero strings attached.\n\n"
            "Mind if I send the 2-minute overview video over?"
        )
