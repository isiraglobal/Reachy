"""Email Outreach Engine - Complete 5-Pillar Architecture.

Implements:
1. Volume (Capacity math & ESP routing)
2. The List (10-row quality gate)
3. Inbox Burn (Daily slope & shadow-ban detection)
4. Systems (Forced menus, sample-first approval, zero overwrite history)
5. Results (500 + 100k dual funnel, PTL tracker, speed-to-lead <5m multiplier)
"""

from .volume_planner import VolumePlan, ESPProviderDetector
from .list_hygiene import TenRowQualityGate, LeadValidationItem
from .inbox_burn_monitor import InboxHealthRecord, FleetHealthMonitor
from .systems_controller import CampaignSystemController, ToneOption, CallToActionOption
from .results_tracker import CampaignResultsModel, DualStrategyCalculator

__all__ = [
    "VolumePlan",
    "ESPProviderDetector",
    "TenRowQualityGate",
    "LeadValidationItem",
    "InboxHealthRecord",
    "FleetHealthMonitor",
    "CampaignSystemController",
    "ToneOption",
    "CallToActionOption",
    "CampaignResultsModel",
    "DualStrategyCalculator",
]
