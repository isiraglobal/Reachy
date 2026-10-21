# Google Maps Leads Agent Tool 🗺️💼

An autonomous lead extractor and enrichment tool built with **agent-browser**, Python, and the **Model Context Protocol (MCP)**. Ready to plug into any AI agent framework (Claude Desktop, Cursor, LangChain, CrewAI, AutoGen, OpenAI Swarm, or standalone scripts).

---

## ⚡ Capabilities

- **Autonomous Maps Extraction**:
  - Searches Google Maps queries (e.g. `"dentists in Austin TX"`, `"coffee shops in Brooklyn"`).
  - Automatically scrolls results feeds with native wheel events.
  - Extracts **Title, Category, Address, Star Rating, Reviews Count, and Google Maps Place URL**.
- **Deep Contact & Web Enrichment**:
  - Finds business websites, official phone numbers, direct emails, and social media handles (Instagram, Facebook, X/Twitter, LinkedIn).
- **Multiple Ways to Run**:
  - 🤖 **MCP Server** (`stdio`) for AI agents (Cursor, Claude Desktop, Antigravity, etc.).
  - 🐍 **Python API** (`from google_maps_leads import GoogleMapsScraper`).
  - 💻 **CLI Tool** (`python -m google_maps_leads.cli ...`).
  - 📊 **Exports to CSV and JSON**.

---

## 🚀 Quickstart

### 1. Requirements

Ensure `agent-browser` is installed and in your PATH:
```bash
agent-browser --version
```

Install Python dependencies:
```bash
pip install -e .
```

---

## 🤖 1. Use as an MCP Tool for AI Agents

Run the MCP server directly over STDIO:
```bash
python3 -m google_maps_leads.mcp_server
```

### Configure in Claude Desktop or Cursor (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "google-maps-leads": {
      "command": "python3",
      "args": [
        "-m",
        "google_maps_leads.mcp_server"
      ],
      "cwd": "/Users/lakshitsinghvi/Documents/Repos/Google-maps-leads"
    }
  }
}
```

The server exposes:
- **`extract_google_maps_leads`**:
  - `query` (string, required): e.g. `"Dentists in Austin, TX"`
  - `limit` (integer, default: 5): Max number of leads
  - `enrich` (boolean, default: true): Extract phone, website, email & social channels
  - `headed` (boolean, default: true): Run browser with visible window

---

## 🐍 2. Use in Python Agent Code (LangChain, CrewAI, Native)

```python
from google_maps_leads import GoogleMapsScraper

# Initialize scraper
scraper = GoogleMapsScraper(headed=True)

# Scrape leads
leads = scraper.scrape_leads(
    query="specialty coffee roasters in Austin TX",
    limit=10,
    enrich=True
)

for lead in leads:
    print(f"Name: {lead.title}")
    print(f"Category: {lead.category}")
    print(f"Phone: {lead.phone}")
    print(f"Website: {lead.website}")
    print(f"Email: {lead.email}")
    print(f"Socials: {lead.social_profiles}")
    print("---")
```

### As a LangChain Tool:
```python
from langchain.tools import tool
from google_maps_leads import GoogleMapsScraper

@tool
def get_business_leads(query: str, limit: int = 5) -> str:
    """Finds and extracts business leads from Google Maps with phone, email, and social profiles."""
    scraper = GoogleMapsScraper(headed=False)
    leads = scraper.scrape_leads(query=query, limit=limit, enrich=True)
    return [lead.to_dict() for lead in leads]
```

---

## 💻 3. Command Line Interface (CLI)

```bash
# Print leads to terminal
python3 -m google_maps_leads.cli "dentists in Austin TX" --limit 5

# Export directly to CSV
python3 -m google_maps_leads.cli "roofing companies in Miami FL" --limit 20 -o leads.csv

# Export directly to JSON
python3 -m google_maps_leads.cli "boutique hotels in Paris" --limit 10 -o leads.json

# Headless mode (no visible browser window)
python3 -m google_maps_leads.cli "plumbers in Chicago" --limit 10 --headless -o plumbers.csv
```

---

## 📂 Project Structure

```
Google-maps-leads/
├── google_maps_leads/
│   ├── __init__.py       # Package exports
│   ├── models.py         # Lead dataclass & serialization
│   ├── scraper.py        # Core agent-browser scraper + enrichment engine
│   ├── mcp_server.py     # MCP Server for Cursor / Claude / Agents
│   └── cli.py            # CLI entry point and CSV/JSON exporter
├── pyproject.toml        # Package setup and dependencies
└── README.md             # Complete documentation
```
