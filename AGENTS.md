# AGENTS.md — Autonomous Agent Operational Guide for Reachy

Welcome, Agent. This repository (**Reachy** by **ISIRA Automations**) is configured for 100% headless, programmatic execution across CLI agents (Claude Code, Antigravity, Cursor, Codex, OpenHands, Windsurf, custom LangChain/CrewAI swarms).

Follow this specification to self-bootstrap, diagnose environment dependencies, discover leads, enrich contact details, and execute compliant cold outreach without human intervention.

---

## 🧭 System Architecture & Directory Map

```text
Reachy/
├── AGENTS.md                        # <- YOU ARE HERE: Machine-readable agent instruction manual
├── README.md                        # Human/Repo overview & SEO presentation
├── pyproject.toml                   # Python dependencies & CLI console entrypoints
│
├── google_maps_leads/               # ⚙️ BROWSER ENGINE & MCP PROTOCOL SERVER
│   ├── browser_test.py              # Autonomous Chrome headless verification tool
│   ├── scraper.py                   # Maps DOM crawler & authority parser
│   ├── models.py                    # Lead data schemas (dataclass)
│   ├── cli.py                       # CLI endpoint (`reachy-leads`)
│   └── mcp_server.py                # Model Context Protocol stdio server (`reachy-mcp`)
│
├── leads/                           # 📍 LEAD DISCOVERY & CONTACT ENRICHMENT
│   ├── README.md                    # Data schemas & validation benchmark guide
│   ├── contact_enricher.py          # Cloudflare XOR cipher decoder & JSON-LD parser
│   ├── philly_venues_1000.json      # Resolved lead dataset (phone numbers & booking emails)
│   ├── leads_1000.json              # 1,000 raw deduplicated business records
│   ├── sample_leads.csv             # CRM/Spreadsheet export
│   └── run_1000_leads_audit.py      # Concurrent HTTP domain reachability auditor
│
└── email_outreach/                  # ✉️ MULTI-INBOX COLD DELIVERY ENGINE
    ├── README.md                    # Outreach architecture & multi-inbox setup
    ├── cold_email_engine.py         # Multi-fleet dispatcher (Aaron Shepherd 5 Truths)
    ├── inboxes.json                 # Connected Google Workspace & M365 accounts
    └── final_outreach_execution_report.json # Single consolidated audit log
```

---

## 🛠️ Step 1: Self-Bootstrap Environment

Run the following commands in the workspace root to prepare the Python virtual environment:

```bash
# 1. Install dependencies in editable mode
pip install -e .

# 2. Verify installed console scripts
reachy-leads --help
reachy-mcp --help
```

---

## 🧪 Step 2: Headless Browser Self-Diagnostic

Before running any scraping or lead discovery task, execute the autonomous browser diagnostic tool. This verifies that Google Chrome / Chromium is installed, can run without a physical display (`--headless=new`), and can inspect the DOM:

```bash
python3 google_maps_leads/browser_test.py
```

### Expected Exit Status:
- **Exit code `0`**: All 4 checks passed (binary located, headless launched, DOM loaded, page title verified). Proceed to scraping.
- **Exit code `1`**: Chrome binary missing or permissions error.
  - On Ubuntu/Debian: `sudo apt-get install -y google-chrome-stable` or `sudo apt-get install -y chromium-browser`
  - On macOS: Ensure Google Chrome is in `/Applications/Google Chrome.app`.

---

## 📍 Step 3: Autonomous Lead Finding (Google Maps)

### Option A: Using the CLI Entrypoint
```bash
# Scrape 20 coffee roasters in Portland OR and export directly to JSON
reachy-leads "Coffee roasters in Portland OR" --limit 20 --output leads/portland_coffee.json

# Scrape venues and export to CSV
reachy-leads "Wedding venues in Philadelphia PA" --limit 50 --output leads/philly_venues.csv
```

### Option B: Programmatic Python Usage in Agent Workflows
```python
from google_maps_leads.scraper import GoogleMapsScraper

# Always pass headed=False for headless server environments
scraper = GoogleMapsScraper(headed=False)
leads = scraper.scrape_leads(
    query="Dentists in Austin TX",
    limit=25,
    enrich=True  # Automatically navigates websites to gather emails & socials
)

# Convert to list of standard dictionaries
results = [lead.to_dict() for lead in leads]
```

---

## 📞 Step 4: Multi-Layer Contact & Phone Enrichment

When you have a raw list of businesses with website URLs or Maps URLs, pass them through the multi-layer contact enricher:

```bash
python3 leads/contact_enricher.py
```

### What `contact_enricher.py` handles automatically:
1. **Google Maps Detail Panes**: Extracts direct office phone numbers (`data-item-id="phone"`) and canonical authority domains.
2. **Cloudflare XOR Cipher Decoder**: Reverses email obfuscation hex strings (`data-cfemail` & `/cdn-cgi/l/email-protection#<hex>`) to retrieve hidden emails.
3. **Schema.org JSON-LD Resolution**: Parses `<script type="application/ld+json">` for `LocalBusiness`, `Organization`, and `Restaurant` schema entities.
4. **Subpage Traversal**: Automatically requests `/contact`, `/events`, `/private-events`, and `/book` for corporate inquiries.
5. **Phone Formatting**: Standardizes numbers into E.164 or US formatted `+1 (XXX) XXX-XXXX`.

---

## ✉️ Step 5: Multi-Inbox Cold Email Outreach Engine

The outreach engine strictly follows **Aaron Shepherd's 20M Send Rules (The 5 Truths)** and the **5-Pillar Architecture**.

### 1. Configure Attached Inboxes (`email_outreach/inboxes.json`)
Inspect or update `email_outreach/inboxes.json` with sending accounts across multiple domains:

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

### 2. Execute the Outreach Dispatcher & Quality Gate
```bash
python3 email_outreach/cold_email_engine.py
```

### Built-in Guardrails Handled by the Engine:
- **10-Row Quality Gate**: Halts immediately if $\ge 2$ of 10 sampled records fail DNS or MX checks.
- **ESP Provider Matching**: Routes Google Workspace recipients to Google Workspace senders, and Microsoft recipients to M365 senders (6.5X deliverability boost).
- **Anti-Burn Daily Cap**: Enforces a strict ceiling of ~10 emails/inbox/day to preserve domain reputation.
- **Work-Done-First Copy Synthesis**: Generates subject lines with 2–3 lowercase words (`quick question`, `venue inquiry`) and avoids generic AI flattery.

---

## 🔌 Step 6: Native Model Context Protocol (MCP) Integration

If you are running inside Cursor, Claude Desktop, or an agent platform supporting MCP, Reachy exposes its tools over `stdio`:

### MCP Configuration Snippet:
```json
{
  "mcpServers": {
    "reachy": {
      "command": "python3",
      "args": ["-m", "google_maps_leads.mcp_server"],
      "cwd": "/path/to/Reachy"
    }
  }
}
```

### Tools exposed over MCP:
- `scrape_leads(query: str, max_results: int = 20, enrich_contacts: bool = True)`
- `search_and_extract(url: str)`

---

## 🚨 Troubleshooting & Edge Cases

| Symptom | Cause | Autonomous Resolution |
| :--- | :--- | :--- |
| `Chrome failed to start: DISPLAY not set` | Running headed on a remote server/VPS | Pass `headed=False` or check `browser_test.py` to ensure `--headless=new` flag is active. |
| Cloudflare block on raw curl | Bot detection / JS challenge | Use `contact_enricher.py` with standard User-Agent headers, or let `scraper.py` fetch the page via the browser instance. |
| Missing phone numbers | Business has no website | Phone numbers are extracted directly from Google Maps place panels (`data-item-id="phone"`), providing 95%+ coverage even when websites lack contact pages. |
| Inboxes exhausted daily limit | Daily cap of 10 reached | Add additional sending inboxes to `inboxes.json` or allow F1 tire rotation to cycle into the next day's allocation. |
