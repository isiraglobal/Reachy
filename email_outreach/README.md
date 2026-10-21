# Cold Outreach & Multi-Inbox Rotation Engine

Part of **Reachy** by **ISIRA Automations**.

This directory houses the autonomous cold email outreach engine built on the **5-Pillar Architecture** and **Aaron Shepherd's 20M Send Rules (The 5 Truths)**.

It features a high-trust **Multi-Email Fleet Manager**, allowing you to attach, manage, and rotate across multiple sending inboxes with ESP provider matching and anti-burn safety throttles.

---

## ⚡ Multi-Email Fleet Attachment & Rotation

You can attach multiple sending email accounts into the outreach engine in two ways:

### 1. Via Configuration File (`inboxes.json`)
Create or edit `inboxes.json` in this directory:

```json
[
  {
    "email": "alex@getreachflow.com",
    "display_name": "Alex Turner",
    "provider": "Google Workspace",
    "daily_limit": 10,
    "age_days": 32,
    "status": "ACTIVE"
  },
  {
    "email": "david@corp-outreach365.com",
    "display_name": "David Vance",
    "provider": "Microsoft 365",
    "daily_limit": 10,
    "age_days": 28,
    "status": "ACTIVE"
  }
]
```

### 2. Programmatically in Python
```python
from email_outreach.cold_email_engine import MultiEmailFleetManager, SenderAccount

fleet = MultiEmailFleetManager()
fleet.attach_multiple([
    SenderAccount(email="alex@getreachflow.com", display_name="Alex Turner", provider="Google Workspace"),
    SenderAccount(email="david@corp-outreach365.com", display_name="David Vance", provider="Microsoft 365")
])
```

### 🛡️ Rotation & Dispatch Behavior
- **Strict Anti-Burn Limits:** Respects Pillar 1 (~10 emails/inbox/day). When an inbox reaches its limit, the engine automatically shifts volume to other available inboxes.
- **ESP Provider Matching:** Automatically pairs target Google Workspace recipients with Google senders, and Microsoft 365 recipients with M365 senders (delivers up to a 6.5X deliverability multiplier).
- **Load-Balanced Round-Robin:** Evenly distributes lead dispatch volume across all attached active accounts.
- **F1 Tire Rotation:** Inboxes run up to day 45; fresh replacement batches are warmed and swapped before domain burnout.

---

## 📐 Aaron Shepherd's 5 Truths of Cold Outreach

1. **Truth 1 (Intent & List Pool):** Go broad, filter strictly for category relevance. Do not over-stack 3–4 intent signals.
2. **Truth 2 (Offers & Risk Reversal):** Drop generic money-back guarantees. Lead with **work done first** (e.g., custom competitor loss audit created upfront with zero risk).
3. **Truth 3 (Subject Lines):** Use **2 to 3 lowercase words**, typed on a phone, looking internal (e.g., `quick question`, `venue inquiry`).
4. **Truth 4 (F1 Tire Rotation):** Warm inboxes for 2 weeks, run live to day 45, reorder and warm replacement batch at day 45 to hot-swap before burnout.
5. **Truth 5 (Personalization):** Eliminate generic AI flattery. Tie **at least 1 real detail** directly to why they buy (e.g., specific review count and star rating in their city).

---

## 📂 Directory Contents

| File | Description |
| :--- | :--- |
| [`cold_email_engine.py`](file:///Users/lakshitsinghvi/Documents/Repos/Google-maps-leads/email_outreach/cold_email_engine.py) | Complete unified outreach engine with multi-email fleet management, 10-row quality gates, F1 tire rotation, copy synthesis, concurrent network audits, and dual-funnel simulations. |
| [`inboxes.json`](file:///Users/lakshitsinghvi/Documents/Repos/Google-maps-leads/email_outreach/inboxes.json) | Configuration file holding all connected sending inboxes, daily limits, providers, and statuses. |
| [`final_outreach_execution_report.json`](file:///Users/lakshitsinghvi/Documents/Repos/Google-maps-leads/email_outreach/final_outreach_execution_report.json) | The final consolidated executive audit report generated automatically upon engine execution. |

---

## 🚀 Running the Outreach Engine

Execute the outreach engine from the repository root:

```bash
python3 email_outreach/cold_email_engine.py
```

The execution will print formatted Rich tables to stdout and write the results to `final_outreach_execution_report.json`.
