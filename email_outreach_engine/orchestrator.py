#!/usr/bin/env python3
"""Executive Orchestrator & CLI for the 5-Pillar Outreach System.

Runs complete simulation & audit on the 1,000 real Google Maps leads gathered in this repo.
"""

import json
import os
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from email_outreach_engine import (
    VolumePlan,
    ESPProviderDetector,
    TenRowQualityGate,
    InboxHealthRecord,
    FleetHealthMonitor,
    CampaignSystemController,
    ToneOption,
    CallToActionOption,
    CampaignResultsModel,
    DualStrategyCalculator
)

console = Console()


def run_system_walkthrough():
    console.print(Panel.fit(
        "[bold cyan]OUTREACH BLUEPRINT ENGINE — 5-PILLAR ARCHITECTURE[/bold cyan]\n"
        "[dim]Volume • The List • Inbox Burn • Systems • Results[/dim]",
        border_style="cyan"
    ))

    # =========================================================================
    # PILLAR 1: VOLUME & ESP MATCHING
    # =========================================================================
    console.print("\n[bold yellow]━━━ 1. VOLUME & INFRASTRUCTURE CAPACITY ━━━[/bold yellow]")
    plan_100k = VolumePlan(target_monthly_volume=100000)
    plan_1m = VolumePlan(target_monthly_volume=1000000)

    vol_table = Table(title="Inbox & Domain Math (10 emails / inbox / day)", header_style="bold magenta")
    vol_table.add_column("Monthly Target", justify="right")
    vol_table.add_column("Daily Volume", justify="right")
    vol_table.add_column("Inboxes Needed", justify="right")
    vol_table.add_column("Domains Needed (3 inboxes/dom)", justify="right")
    vol_table.add_column("Infra Tier", justify="left")

    vol_table.add_row(f"{plan_100k.target_monthly_volume:,}", f"{plan_100k.daily_volume:,}", str(plan_100k.inboxes_needed), str(plan_100k.domains_needed), plan_100k.infra_tier)
    vol_table.add_row(f"{plan_1m.target_monthly_volume:,}", f"{plan_1m.daily_volume:,}", str(plan_1m.inboxes_needed), str(plan_1m.domains_needed), plan_1m.infra_tier)
    console.print(vol_table)

    # Test ESP Detection on sample domains
    sample_domains = ["google.com", "microsoft.com", "stripe.com"]
    esp_table = Table(title="ESP Router (6.5X Reply Multiplier)", header_style="bold green")
    esp_table.add_column("Target Domain")
    esp_table.add_column("Detected Target ESP")
    esp_table.add_column("Recommended Sending ESP")
    esp_table.add_column("Reply Advantage")

    for dom in sample_domains:
        res = ESPProviderDetector.detect_esp_from_domain(dom)
        esp_table.add_row(res["domain"], res["target_esp"], res["recommended_sending_esp"], res["esp_matching_advantage"])
    console.print(esp_table)

    # =========================================================================
    # PILLAR 2: THE LIST & 10-ROW QUALITY GATE
    # =========================================================================
    console.print("\n[bold yellow]━━━ 2. THE LIST (10-ROW QUALITY GATE) ━━━[/bold yellow]")
    console.print("[dim]Rule: If 2 of 10 rows are wrong, STOP and fix the list.[/dim]")

    # Load from our actual generated leads_1000.json
    leads_file = "leads_1000.json"
    if os.path.exists(leads_file):
        with open(leads_file) as f:
            leads = json.load(f)
    else:
        leads = [
            {"title": "Austin Orthodontic Arts", "email": "info@aoarts.com", "category": "Orthodontist", "address": "Austin TX", "reviews_count": 700},
            {"title": "Blunn Creek Family Dental", "email": "contact@blunncreek.com", "category": "Dentist", "address": "Austin TX", "reviews_count": 180}
        ]

    audit = TenRowQualityGate.audit_10_rows(leads, target_region="US")
    
    gate_color = "green" if audit["status"] == "APPROVED_FOR_OUTREACH" else "red"
    console.print(f"Status: [{gate_color} bold]{audit['status']}[/{gate_color} bold] | Error Rate: {audit['error_rate']} (Passed: {audit['passed_rows_count']}/10)")

    gate_table = Table(title="10-Row Audit Verification", header_style="bold blue")
    gate_table.add_column("#", justify="right")
    gate_table.add_column("Company")
    gate_table.add_column("Email")
    gate_table.add_column("Status")
    gate_table.add_column("Notes / Flags")

    for i, item in enumerate(audit["details"], 1):
        st = "[green]PASS[/green]" if item["passed"] else "[red]FAIL[/red]"
        notes = ", ".join(item["errors"]) if item["errors"] else "Clean ICP Match"
        gate_table.add_row(str(i), item["company"][:28], item["email"] or "[italic dim]none[/italic dim]", st, notes)
    console.print(gate_table)

    # =========================================================================
    # PILLAR 3: INBOX BURN & LIFECYCLE MONITORING
    # =========================================================================
    console.print("\n[bold yellow]━━━ 3. INBOX BURN & DELIVERABILITY LIFECYCLE ━━━[/bold yellow]")
    monitor = FleetHealthMonitor()
    
    # Healthy inbox
    monitor.add_inbox(InboxHealthRecord(
        inbox_email="alex@sales-growth.co",
        domain="sales-growth.co",
        age_months=2.5,
        daily_reply_rates_14d=[0.04, 0.04, 0.035, 0.04, 0.038, 0.042, 0.039, 0.04, 0.041, 0.038, 0.04, 0.039, 0.041, 0.04],
        replies_count_14d=6
    ))
    # Degrading slope inbox
    monitor.add_inbox(InboxHealthRecord(
        inbox_email="jordan@reachout-mail.com",
        domain="reachout-mail.com",
        age_months=6.2,
        daily_reply_rates_14d=[0.03, 0.028, 0.025, 0.022, 0.02, 0.018, 0.015, 0.014, 0.012, 0.011, 0.009, 0.008, 0.007, 0.006],
        replies_count_14d=2
    ))
    # Shadow banned inbox
    monitor.add_inbox(InboxHealthRecord(
        inbox_email="outreach@direct-inbox.net",
        domain="direct-inbox.net",
        age_months=7.1,
        bounce_rate=0.0,
        replies_count_14d=0,
        total_sent_14d=140,
        daily_reply_rates_14d=[0.0] * 14
    ))

    fleet_summary = monitor.generate_fleet_report()
    fleet_table = Table(title="Fleet Health & Slope Detection", header_style="bold red")
    fleet_table.add_column("Inbox")
    fleet_table.add_column("Age")
    fleet_table.add_column("14d Avg Reply")
    fleet_table.add_column("Domain Rule")
    fleet_table.add_column("Diagnosis / Action")

    for ev in fleet_summary["evaluations"]:
        fleet_table.add_row(ev["inbox"], f"{ev['age_months']} mos", ev["avg_reply_rate"], ev["domain_rule_status"], ev["action_required"])
    console.print(fleet_table)

    # =========================================================================
    # PILLAR 4: SYSTEMS & COMPOUNDING ERROR PREVENTION
    # =========================================================================
    console.print("\n[bold yellow]━━━ 4. SYSTEMS (RELIABILITY & SAMPLE GATE) ━━━[/bold yellow]")
    controller = CampaignSystemController("Dental ICP Q4 Outreach")
    
    # Forced menus
    v1 = controller.add_copy_version(
        subject="Quick question about {{company}}",
        body="Hi {{name}}, noticed your high patient reviews in {{address}}. We help specialized dental practices acquire 15+ high-ticket implants monthly.",
        tone=ToneOption.DIRECT_VALUE_ADD,
        cta=CallToActionOption.LOW_FRICTION_INTEREST
    )
    console.print(f"[green]✓ Copy Version {v1.version_id} registered using strict tone & CTA menus (Zero text overwrite policy).[/green]")

    # Sample preview gate
    sample_preview = controller.generate_sample_preview(leads[0] if leads else {"title": "Apex Dental", "address": "Austin TX"})
    console.print(f"Sample Render Output: Subject='{sample_preview['rendered_subject']}'")
    console.print(f"Rendered Body Preview:\n[italic dim]{sample_preview['rendered_body']}[/italic dim]")

    # Pass the gate
    controller.approve_sample_gate(True)
    readiness = controller.verify_dispatch_readiness()
    console.print(f"System Guard Score: [bold green]{readiness['system_reliability_score']}[/bold green] (vs un-guarded ~41%) | Approved: {readiness['sample_approved']}")

    # =========================================================================
    # PILLAR 5: RESULTS & SPEED-TO-LEAD ENGINE
    # =========================================================================
    console.print("\n[bold yellow]━━━ 5. RESULTS: RUN THE 500 + THE 100K ━━━[/bold yellow]")
    dual = DualStrategyCalculator.simulate_dual_funnel()
    
    funnel_table = Table(title="Dual Strategy Outcomes", header_style="bold cyan")
    funnel_table.add_column("Funnel")
    funnel_table.add_column("Volume")
    funnel_table.add_column("Reply Rate")
    funnel_table.add_column("Replies")
    funnel_table.add_column("Meetings Booked (<5m Speed)")
    funnel_table.add_column("PTL (Prospects-To-Lead)")

    t500 = dual["tier_500_boutique"]
    t100k = dual["tier_100k_scale"]
    funnel_table.add_row(t500["strategy"], f"{t500['volume']:,}", t500["reply_rate"], str(t500["replies"]), str(t500["meetings"]), f"{t500['ptl']:.1f}")
    funnel_table.add_row(t100k["strategy"], f"{t100k['volume']:,}", t100k["reply_rate"], str(t100k["replies"]), str(t100k["meetings"]), f"{t100k['ptl']:.1f}")
    console.print(funnel_table)

    console.print(Panel(
        f"[bold green]Combined Meetings Target: {dual['combined_meetings_generated']} Meetings[/bold green]\n"
        f"[bold white]Speed-To-Lead Multiplier:[/bold white] Responding in < 5 mins locks in ~80% meeting conversion (vs ~20% for slow responses).\n"
        f"[bold white]Benchmark:[/bold white] Both funnels achieve PTL < 500 (extremely solid efficiency).",
        border_style="green"
    ))


if __name__ == "__main__":
    run_system_walkthrough()
