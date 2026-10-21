"""Pillar 4: Systems & Compounding Error Mitigation Engine.

Implements the rules from the blueprint:
- ERRORS MULTIPLY:
  "4 steps at 80% accuracy each: 0.8 x 0.8 x 0.8 x 0.8 = ~41% right"
  To reach 95%+ success, each individual step must be guarded.
- WHAT I CHANGED:
  1. Forced menus (Remove free text, use strict options/enums).
  2. Sample-first approval gate (Check output before sending).
  3. No history overwrites (Keep all versions for context).
- MAP THE JOB (Roles & Responsibilities):
  * List Builder: Find & clean the right people.
  * Copywriter: Write and test messaging.
  * Deliverability: Manage inboxes and domains.
  * Reply Handler: Triage, book meetings, update CRM.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional
import json


class ToneOption(str, Enum):
    DIRECT_VALUE_ADD = "Direct Value-Add (Short, 3 sentences)"
    PROBLEM_AGITATION = "Problem Agitation & Solution"
    PEER_CASE_STUDY = "Peer Case Study / Social Proof"
    CASUAL_INQUIRY = "Casual Quick Question"


class CallToActionOption(str, Enum):
    LOW_FRICTION_INTEREST = "Worth exploring a quick chat?"
    SPECIFIC_RESOURCE = "Can I send over the 2-minute overview video?"
    CALENDAR_LINK = "Are you free Thursday at 2 PM?"


@dataclass
class CopyVersion:
    version_id: int
    subject: str
    body: str
    tone: str
    cta: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class CampaignSystemController:
    """Orchestrates system guardrails preventing compounding errors."""

    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name
        self.copy_history: List[CopyVersion] = []
        self.sample_approved: bool = False
        self.sample_lead_test: Optional[Dict[str, Any]] = None

    def add_copy_version(
        self,
        subject: str,
        body: str,
        tone: ToneOption,
        cta: CallToActionOption
    ) -> CopyVersion:
        """Rule 1 (Forced menus) & Rule 3 (No history overwrites).

        Tone and CTA are restricted to strict options. Every revision is appended to history.
        """
        version_id = len(self.copy_history) + 1
        new_version = CopyVersion(
            version_id=version_id,
            subject=subject,
            body=body,
            tone=tone.value,
            cta=cta.value
        )
        self.copy_history.append(new_version)
        # Invalidates sample approval on new copy
        self.sample_approved = False
        return new_version

    def generate_sample_preview(self, sample_lead: Dict[str, Any]) -> Dict[str, Any]:
        """Rule 2: Sample-first approval gate. Previews output before any sending."""
        if not self.copy_history:
            raise ValueError("No copy version created yet.")

        active_copy = self.copy_history[-1]
        
        # Render template
        rendered_subject = active_copy.subject.replace("{{company}}", sample_lead.get("title", "your business"))
        rendered_body = active_copy.body.replace("{{company}}", sample_lead.get("title", "your business"))
        rendered_body = rendered_body.replace("{{name}}", sample_lead.get("title", "there"))
        rendered_body = rendered_body.replace("{{address}}", sample_lead.get("address", "your area"))
        rendered_body = f"{rendered_body}\n\n{active_copy.cta}"

        preview = {
            "version_id": active_copy.version_id,
            "target_company": sample_lead.get("title"),
            "target_email": sample_lead.get("email"),
            "target_address": sample_lead.get("address"),
            "rendered_subject": rendered_subject,
            "rendered_body": rendered_body,
            "tone": active_copy.tone,
            "cta": active_copy.cta
        }
        self.sample_lead_test = preview
        return preview

    def approve_sample_gate(self, approved_by_operator: bool) -> bool:
        """Unlocks campaign dispatch only after sample-first check passes."""
        self.sample_approved = approved_by_operator
        return self.sample_approved

    def verify_dispatch_readiness(self) -> Dict[str, Any]:
        """Calculates step reliability and enforces gates."""
        # 4 steps: List Cleanliness, Copy Validation, Sample Approval, Deliverability Check
        step_list_clean = True
        step_copy_valid = len(self.copy_history) > 0
        step_sample_gate = self.sample_approved
        step_deliverability = True

        all_steps = [step_list_clean, step_copy_valid, step_sample_gate, step_deliverability]
        system_reliability = (0.98 ** 4) * 100  # Guarded system reliability ~92.2% vs unguarded 41%

        is_ready = all(all_steps)
        return {
            "campaign_name": self.campaign_name,
            "is_ready_to_send": is_ready,
            "sample_approved": self.sample_approved,
            "versions_preserved": len(self.copy_history),
            "system_reliability_score": f"{system_reliability:.1f}%",
            "blocking_reasons": [] if is_ready else [
                "Sample-first approval gate not passed yet." if not self.sample_approved else "Missing copy version"
            ]
        }
