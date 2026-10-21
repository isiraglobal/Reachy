# Google Maps Leads & Cold Outreach Automation System 🗺️✉️

A modular, production-ready system for autonomous **Google Maps lead generation** and **multi-inbox cold email outreach**. 

Built with **agent-browser** for headless/headed browser execution (no screen required for CLI agents), **Model Context Protocol (MCP)** support, and an enterprise outreach engine following the **5-Pillar Architecture** and **Aaron Shepherd's 20M Send Rules (The 5 Truths)**.

---

## 📂 Repository Structure

```text
Google-maps-leads/
├── leads/                           # 📍 LEADS GATHERING & DISCOVERY
│   ├── README.md                    # Lead data schema & audit documentation
│   ├── leads_1000.json              # 1,000 real scraped business leads
│   ├── sample_leads.csv             # Exported spreadsheet of business leads
│   ├── verified_leads.json          # Verified deep-crawl samples
│   ├── verification_audit.json      # Network audit results (<5-10% error rate)
│   └── run_1000_leads_audit.py      # Lead reachability & network verification tool
│
├── email_outreach/                  # ✉️ COLD OUTREACH & MULTI-INBOX ENGINE
│   ├── README.md                    # Outreach architecture & multi-email attachment docs
│   ├── cold_email_engine.py         # Complete unified outreach execution engine
│   ├── inboxes.json                 # Attached sending email accounts (Google + M365)
│   └── final_outreach_execution_report.json # Single consolidated audit report
│
├── google_maps_leads/               # ⚙️ CORE BROWSER SCRAPER & MCP PACKAGE
│   ├── __init__.py                  # Package exports
│   ├── models.py                    # Lead data model (dataclass)
│   ├── scraper.py                   # Google Maps extractor & website/email enrichment
│   ├── browser_test.py              # Autonomous Chrome browser self-test for CLI agents
│   ├── mcp_server.py                # MCP Server over stdio for Claude/Cursor/Agents
│   └── cli.py                       # CLI interface for scraping to CSV/JSON
│
├── pyproject.toml                   # Python dependencies & build config
└── README.md                        # Complete project guide
```

---

## ⚡ Key Capabilities

### 1. Lead Gathering & Email/Phone Discovery (`leads/`)
- **Direct Maps Extraction**: Extracts business name, cuisine/category, address, star rating, review count, and direct Google Maps Place URLs.
- **Deep Contact Enrichment**: Automatically navigates place authority links and crawls company websites (with Cloudflare & JS-render handling) to discover:
  - **Phone Numbers** (direct office line, formatted `+1 ...`)
  - **Verified Emails** (`info@`, `contact@`, `events@`, `admin@`)
  - **Official Websites & Social Profiles** (Instagram, Facebook, LinkedIn, X/Twitter).

### 2. Multi-Email Fleet Attachment & Rotation (`email_outreach/`)
- **Multi-Account Rotation**: Attach unlimited inboxes across Google Workspace and Microsoft 365 via `inboxes.json` or Python.
- **ESP Provider Matching (6.5X Reply Multiplier)**: Dynamically pairs Google recipients with Google senders, and Microsoft 365 recipients with M365 senders.
- **Strict Anti-Burn Throttle**: Automatically enforces ~10 emails/inbox/day (Pillar 1).
- **F1 Tire Rotation**: Inboxes run up to day 45; fresh replacement batches are reordered and warmed at day 45 to hot-swap before domain burnout.
- **10-Row Quality Gate**: Audits list quality; hard-halts if $\ge 2$ of 10 rows fail (prevents domain blacklisting).
- **Work-Done-First Copy**: Subject lines formatted in 2–3 lowercase words (`quick question`, `audit for company`). Real detail personalization (exact review counts and ratings in their city).

### 3. Autonomous Browser Testing for CLI Agents (`google_maps_leads/browser_test.py`)
- Agents running in terminal environments (SSH, VPS, tmux, Docker) can autonomously test and verify Chrome browser connectivity without requiring a physical monitor or human intervention.

---

## 🚀 Quickstart

### 1. Install Dependencies

Ensure `agent-browser` is installed:
```bash
npm install -g agent-browser
```

Install Python dependencies:
```bash
pip install -e .
```

### 2. Run Autonomous Browser Self-Test
Verify that Chrome browser automation is healthy and ready for headless CLI runs:
```bash
python3 google_maps_leads/browser_test.py
```
*(Optionally run with visible window using `--headed`: `python3 google_maps_leads/browser_test.py --headed`)*

---

## 💻 Usage Guides

### A. Extracting Leads from the Command Line

```bash
# Extract 10 leads with phone, website, and email discovery
python3 -m google_maps_leads.cli "dentists in Austin TX" --limit 10 -o leads.json

# Run in headless mode (perfect for background VPS/CLI runs)
python3 -m google_maps_leads.cli "restaurants in Philadelphia PA" --limit 25 --headless -o philly.csv
```

### B. Running as an MCP Tool in AI Agents

Plug directly into Cursor, Claude Desktop, or custom agent swarms via `stdio`:
```json
{
  "mcpServers": {
    "google-maps-leads": {
      "command": "python3",
      "args": ["-m", "google_maps_leads.mcp_server"],
      "cwd": "/path/to/Google-maps-leads"
    }
  }
}
```

### C. Running the Outreach Engine & Dual-Funnel Simulator

Run the complete 5-Pillar & Aaron Shepherd 5-Truths outreach pipeline:
```bash
python3 email_outreach/cold_email_engine.py
```

This performs:
1. **Infrastructure volume math** (100k sends/mo fleet sizing).
2. **The 10-Row Quality Gate audit**.
3. **Multi-Email attached inbox rotation & ESP matching**.
4. **F1 Tire inbox health analysis**.
5. **Work-Done-First copy synthesis**.
6. **Concurrent network verification audit (<5-10% error rate)**.
7. **Dual-funnel projection** (The 500 @ 80% speed-to-lead + The 100k scale).
8. **Generates single unified report**: `email_outreach/final_outreach_execution_report.json`.

---

## ✉️ Attaching Multiple Sending Emails

Add your sending mailboxes to [`email_outreach/inboxes.json`](file:///Users/lakshitsinghvi/Documents/Repos/Google-maps-leads/email_outreach/inboxes.json):

```json
[
  {
    "email": "alex@yourbrand.com",
    "display_name": "Alex Turner",
    "provider": "Google Workspace",
    "daily_limit": 10,
    "age_days": 32,
    "status": "ACTIVE"
  },
  {
    "email": "david@yourbrand-outreach.com",
    "display_name": "David Vance",
    "provider": "Microsoft 365",
    "daily_limit": 10,
    "age_days": 28,
    "status": "ACTIVE"
  }
]
```

Or programmatically in Python:
```python
from email_outreach.cold_email_engine import MultiEmailFleetManager, SenderAccount

fleet = MultiEmailFleetManager()
fleet.attach_multiple([
    SenderAccount(email="alex@domain.com", display_name="Alex", provider="Google Workspace"),
    SenderAccount(email="david@domain.com", display_name="David", provider="Microsoft 365")
])
```

---

## 🛡️ License & Contributing

Built for high-performance lead generation and enterprise cold email deliverability. Contributions and pull requests welcome.
