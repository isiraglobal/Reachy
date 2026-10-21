# Cold Outreach Engine & Campaign Execution

This directory houses the unified cold email outreach engine built on the **5-Pillar Architecture** and **Aaron Shepherd's 20M Send Rules (The 5 Truths)**.

---

## Architecture Overview

### Aaron Shepherd's 5 Truths
1. **Truth 1 (Intent & List Pool):** Go broad, filter strictly for category relevance. Do not over-stack 3–4 intent signals into a tiny, exhausted pool.
2. **Truth 2 (Offers & Risk Reversal):** Drop generic money-back guarantees. Lead with **work done first** (e.g., custom competitor loss audit created upfront with zero risk).
3. **Truth 3 (Subject Lines):** Use **2 to 3 lowercase words**, typed on a mobile phone, looking internal (e.g., `quick question`, `implant growth`).
4. **Truth 4 (F1 Tire Rotation):** Warm inboxes for 2 weeks, run live to day 45, reorder and warm a replacement batch at day 45 to hot-swap before burnout.
5. **Truth 5 (Personalization):** Eliminate generic AI flattery. Tie **at least 1 real detail** directly to why they buy (e.g., specific review counts and star rating in their city).

### The 5-Pillar Operational System
- **Pillar 1 (Volume):** Enforces 10 emails/inbox/day, max 3 inboxes/domain. Calculates fleet sizing (454 active inboxes + 158 warming buffer = 612 total for 100k/mo).
- **Pillar 2 (The List):** 10-row quality gate. If $\ge 2$ of 10 rows fail (missing email, free providers like `@gmail`, competitor terms), the campaign halts immediately.
- **Pillar 3 (Inbox Burn):** Tracks 2-week downward trends and shadow-ban conditions ($0\%$ bounce + $0$ replies).
- **Pillar 4 (Systems):** Versioned copy packages and sample-first validation.
- **Pillar 5 (Results):** Dual funnel model:
  - **The 500 (Boutique):** 5% reply rate $\rightarrow$ 25 replies $\rightarrow$ 20 meetings booked via $< 5$ min speed-to-lead ($80\%$ conversion) $\rightarrow$ PTL score: **25.0**.
  - **The 100k (Universal Broad Scale):** 1% reply rate $\rightarrow$ 1,000 replies $\rightarrow$ 500 meetings booked $\rightarrow$ PTL score: **200.0**.

---

## Directory Contents

| File | Description |
| :--- | :--- |
| `cold_email_engine.py` | Complete unified outreach engine implementing fleet sizing, 10-row quality gates, F1 tire rotation, copy synthesis, concurrent network audits, and dual-funnel simulations. |
| `final_outreach_execution_report.json` | The final consolidated executive audit report generated automatically upon engine execution. |

---

## Running the Engine

Execute the outreach engine from the repository root:

```bash
python3 outreach/cold_email_engine.py
```

Or from within the `outreach` directory:

```bash
cd outreach && python3 cold_email_engine.py
```

The execution will print formatted Rich tables to stdout and write the results to `final_outreach_execution_report.json`.
