# Reachy

<div align="center">

<p align="center">
  <img src="https://img.shields.io/badge/Maintained%20by-ISIRA%20Automations-0052FF?style=for-the-badge&logo=shield" alt="ISIRA Automations" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python" alt="Python Version" />
  <img src="https://img.shields.io/badge/Protocol-Model%20Context%20Protocol%20(MCP)-blueviolet?style=for-the-badge" alt="MCP Supported" />
  <img src="https://img.shields.io/badge/Architecture-5--Pillar%20%7C%205%20Truths-success?style=for-the-badge" alt="Enterprise Outreach" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License" />
</p>

### **The Enterprise B2B Lead Finding, Contact Enrichment & Multi-Inbox Cold Outreach Engine**
*Engineered by **ISIRA Automations** for AI Coding Agents, Sales Engineers, and High-Volume B2B Growth Teams.*

[Features](#-core-features) • [Architecture](#-system-architecture) • [Quickstart](#-quickstart) • [Agent Guide (AGENTS.md)](file:///Users/lakshitsinghvi/Documents/Repos/Google-maps-leads/AGENTS.md) • [Lead Discovery](#-lead-discovery--enrichment-pipeline) • [Multi-Inbox Outreach](#-multi-inbox-outreach-engine) • [MCP Server](#-model-context-protocol-mcp-integration) • [Autonomous CLI Diagnostics](#-autonomous-cli-agent-diagnostics)

---

</div>

## 📌 Executive Summary

**Reachy** is an autonomous, production-ready lead acquisition and cold email delivery platform developed by **ISIRA Automations**. It solves the two hardest challenges in modern outbound sales:

1. **Precision B2B Discovery & Deep Contact Resolution (`leads/`)**: Bypasses anti-bot friction, parses single-page applications, decodes Cloudflare XOR email obfuscation, extracts Schema.org JSON-LD structured data, and correlates Google Maps place authority panes to deliver direct business phone numbers and decision-maker contact emails.
2. **Enterprise Multi-Inbox Rotation & Outreach Engine (`email_outreach/`)**: Built on Aaron Shepherd’s 20M send architecture ("The 5 Truths"), supporting multi-account fleet attachment, automated ESP provider matching (Google-to-Google, M365-to-M365 for a 6.5X deliverability boost), strict anti-burn throttles (10 emails/inbox/day), and F1 tire rotation before domain fatigue.

---

## ⚡ Core Features

| Pillar | Capability | Technical Advantage |
| :--- | :--- | :--- |
| 📍 **Maps Lead Discovery** | Headless Google Maps extractor with coordinate-based radius scanning. | Collects verified Place IDs, review volume, star ratings, categories, and street addresses without third-party API keys. |
| 📞 **Direct Phone Resolution** | Extracts primary business lines from Google Maps authority detail panels. | Produces **>95% phone number resolution** normalized to E.164 / `+1 (XXX) XXX-XXXX`. |
| 🛡️ **Cloudflare XOR Decryption** | Decodes `data-cfemail` & `/cdn-cgi/l/email-protection#<hex>` tags. | Unlocks inquiry and corporate emails that standard regex and legacy scrapers miss. |
| 🧬 **Schema.org JSON-LD Parsing** | Crawls subpages (`/contact`, `/events`, `/about`) for JSON-LD schemas. | Extracts structured `telephone` and `email` properties from `LocalBusiness` and `Organization` entities. |
| 📬 **Multi-Inbox Fleet Rotation** | Attach unlimited Google Workspace and Microsoft 365 accounts via `inboxes.json`. | Dynamically balances daily volume and handles hot-swapping under F1 tire rotation schedules. |
| 🎯 **ESP Provider Matching** | Detects recipient MX records (Google vs. Microsoft 365). | Route Google leads to Google senders and Microsoft leads to M365 senders (6.5X deliverability multiplier). |
| 🤖 **Autonomous CLI Verification** | Built-in headless Chrome self-test tool (`reachy-browser-test`). | Allows CLI agents (Cursor, Claude Code, Terminal Bots) to self-test browser health in headless environments without displays. |
| 🔌 **MCP Server Ready** | Native Model Context Protocol (MCP) server over `stdio`. | Expose lead extraction directly as native tools for Claude, Gemini, Cursor, or AI agent swarms. |

---

## 📂 System Architecture

```text
Reachy/
├── leads/                               # 📍 CORE LEAD DISCOVERY & ENRICHMENT
│   ├── README.md                        # Lead schemas, data dictionary & benchmarks
│   ├── contact_enricher.py              # Cloudflare XOR decoder, JSON-LD parser & subpage crawler
│   ├── philly_venues_1000.json          # Production dataset: direct phone numbers (95%+) & booking emails
│   ├── leads_1000.json                  # 1,000 real deduplicated business leads (names, ratings, addresses)
│   ├── sample_leads.csv                 # Ready-to-import CSV representation for spreadsheets/CRMs
│   ├── verified_leads.json              # Deep-crawl validation samples
│   ├── verification_audit.json          # Concurrent network audit logs (<5-10% error rate)
│   └── run_1000_leads_audit.py          # Standalone network audit & domain accessibility tester
│
├── email_outreach/                      # ✉️ COLD OUTREACH & MULTI-INBOX ENGINE
│   ├── README.md                        # Outreach architecture & multi-account documentation
│   ├── cold_email_engine.py             # Multi-inbox fleet manager, 5-Pillar rules & copy synthesizer
│   ├── inboxes.json                     # Connected sending accounts (Google Workspace + M365)
│   └── final_outreach_execution_report.json # Single consolidated executive outreach audit report
│
├── google_maps_leads/                   # ⚙️ CORE BROWSER SCRAPER & MCP PACKAGE
│   ├── __init__.py                      # Package exports
│   ├── models.py                        # Lead data model (dataclass)
│   ├── scraper.py                       # Maps extractor & website/email enrichment
│   ├── browser_test.py                  # Autonomous Chrome self-test tool for CLI agents
│   ├── mcp_server.py                    # FastMCP Server over stdio for AI Agents
│   └── cli.py                           # CLI interface for scraping to CSV/JSON
│
├── pyproject.toml                       # Python package specification & CLI entrypoints
└── README.md                            # Complete system documentation
```

---

## 🚀 Quickstart

### 1. Installation

Clone and install dependencies with Python 3.10+:

```bash
git clone https://github.com/isiraglobal/Reachy.git
cd Reachy
pip install -e .
```

Ensure Chrome / Chromium is installed on your machine or server.

---

## 📍 Lead Discovery & Enrichment Pipeline

### Running the Multi-Layer Contact Enricher
Extract phone numbers, decode Cloudflare emails, and parse Schema.org metadata:

```bash
python3 leads/contact_enricher.py
```

### Lead Data Output Format
Each lead output conforms to strict data typing:

```json
{
  "title": "Fitler Club",
  "category": "Event Venue & Private Club",
  "rating": 4.6,
  "reviews_count": 340,
  "phone": "+1 (215) 575-9092",
  "website": "https://fitlerclub.com",
  "email": "events@fitlerclub.com",
  "address": "24 S 24th St, Philadelphia, PA 19103",
  "url": "https://www.google.com/maps/place/...",
  "social_profiles": [
    "https://instagram.com/fitlerclub"
  ],
  "extra_details": {
    "source": "google_maps_authority_pane",
    "verified": true
  }
}
```

---

## ✉️ Multi-Inbox Outreach Engine

Reachy includes an enterprise cold outreach engine based on **Aaron Shepherd's 20M Send Rules (The 5 Truths)**:

1. **Truth 1 (Intent & List Pool)**: Broad targeting with strict category relevance.
2. **Truth 2 (Offers & Risk Reversal)**: Zero generic money-back guarantees; lead with upfront "work done first" (e.g. customized competitive audit).
3. **Truth 3 (Subject Lines)**: 2 to 3 lowercase words typed on a mobile phone (e.g., `quick question`, `venue inquiry`).
4. **Truth 4 (F1 Tire Rotation)**: Warm accounts for 14 days, send up to day 45, reorder and warm replacement batches at day 45 to hot-swap before domain burnout.
5. **Truth 5 (Personalization)**: Real detail personalization tying reviews, ratings, and metro data directly to buyer motivation.

### Connecting Multiple Inboxes (`email_outreach/inboxes.json`)
Configure sending accounts across multiple domains:

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

### Running the Outreach Campaign & Audit
```bash
python3 email_outreach/cold_email_engine.py
```

The engine automatically applies the **10-Row Quality Gate** and exports execution metrics to `email_outreach/final_outreach_execution_report.json`.

---

## 🔌 Model Context Protocol (MCP) Integration

Reachy can run as a standard MCP server over `stdio` to provide AI tools directly to Claude Desktop, Cursor, or autonomous agent frameworks.

Add the following to your `claude_desktop_config.json` or cursor settings:

```json
{
  "mcpServers": {
    "reachy": {
      "command": "python3",
      "args": [
        "-m",
        "google_maps_leads.mcp_server"
      ],
      "cwd": "/path/to/Reachy"
    }
  }
}
```

### Available MCP Tools:
- `scrape_leads(query="restaurants in philadelphia", max_results=50, enrich_contacts=True)`: Discovers businesses, extracts phone numbers, and crawls websites for contact emails.
- `search_and_extract(url="https://...")`: Extracts structured schema and business information from any target URL.

---

## 🧪 Autonomous Browser Download, Testing & Errand Runner

For AI agents running in headless environments (VPS, tmux, Docker, GitHub Actions, cloud VMs), Reachy provides complete browser auto-downloading, self-test diagnostics, and autonomous web errand execution without requiring a physical monitor or human user:

### 1. Download & Install Browser Binaries
```bash
reachy-browser-install --install
```

### 2. Autonomous Browser Self-Diagnostics
```bash
python3 google_maps_leads/browser_test.py
# or via CLI:
reachy-browser-test
```

### 3. Run Autonomous Web Errands
Dispatch your agent to inspect target pages, fetch DOM states, or capture screenshots:
```bash
# Evaluate DOM state:
reachy-browser-install --url "https://www.google.com/maps" --task eval

# Capture interactive accessibility snapshot:
reachy-browser-install --url "https://example.com" --task snapshot

# Capture full-page screenshot:
reachy-browser-install --url "https://example.com" --task screenshot
```

Output:
```text
============================================================
Autonomous Chrome Browser Diagnostic Check
============================================================
[1/4] Detecting Chrome binary...
   -> Found Chrome binary at: /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
[2/4] Verifying headless execution flag...
   -> Chrome launched successfully in headless mode.
[3/4] Testing navigation and DOM extraction...
   -> Successfully loaded test page: Example Domain
[4/4] Extracting page content and title...
   -> Page title verified: 'Example Domain'
============================================================
RESULT: ALL CHECKS PASSED (4/4) - Browser is ready for autonomous scraping!
============================================================
```

---

## 🛡️ License & Attributions

Developed and maintained by **[ISIRA Automations](https://github.com/isiraglobal)**.  
Released under the **MIT License**.
