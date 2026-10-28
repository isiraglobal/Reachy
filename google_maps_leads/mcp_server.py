"""Model Context Protocol server for Reachy.

Exposes lead discovery and browser diagnostics over stdio. Email credentials
and campaign execution are not accessible through this server.
"""

from __future__ import annotations

import logging
from typing import Any

import bs4

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reachy_mcp")


def _scrape(query: str, limit: int, enrich: bool, headed: bool) -> list[dict[str, Any]]:
    from .scraper import GoogleMapsScraper

    clamped = min(max(1, int(limit)), 100)
    scraper = GoogleMapsScraper(headed=headed)
    try:
        leads = scraper.scrape_leads(query=query, limit=clamped, enrich=enrich)
        return [lead.to_dict() for lead in leads]
    finally:
        scraper.close()


def _extract_url(url: str) -> dict[str, Any]:
    from reachy.web import extract_contacts_from_html, fetch_html

    html, final_url = fetch_html(url, timeout=15)
    soup = bs4.BeautifulSoup(html, "html.parser")
    contacts = extract_contacts_from_html(html, final_url)
    return {
        "url": final_url,
        "title": soup.title.get_text(strip=True) if soup.title else None,
        "emails": contacts["emails"],
        "phones": contacts["phones"],
        "json_ld_types": contacts.get("json_ld_types", []),
    }


try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # mcp 2.x renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP

mcp = FastMCP("reachy")


@mcp.tool()
def extract_google_maps_leads(
    query: str,
    limit: int = 10,
    enrich: bool = True,
    headed: bool = False,
) -> list[dict[str, Any]]:
    """Search Google Maps and return normalized lead dictionaries.

    Browser automation is used only where permitted. CAPTCHAs and access
    controls are never bypassed; blocked sources return an empty result.
    """
    return _scrape(query, limit, enrich, headed)


@mcp.tool()
def scrape_leads(
    query: str,
    max_results: int = 20,
    enrich_contacts: bool = True,
    headed: bool = False,
) -> list[dict[str, Any]]:
    """Alias used by agent integrations."""
    return _scrape(query, max_results, enrich_contacts, headed)


@mcp.tool()
def search_and_extract(url: str) -> dict[str, Any]:
    """Fetch one public URL and extract title, emails, phones, and JSON-LD types."""
    try:
        return _extract_url(url)
    except ValueError as exc:
        return {"error": str(exc)}


@mcp.tool()
def browser_diagnostics(headed: bool = False, url: str = "") -> dict[str, Any]:
    """Check Playwright/Chromium availability and report remediation steps."""
    from reachy.browser import check_browser
    from reachy.web import validate_public_url

    if url:
        try:
            validate_public_url(url)
        except ValueError as exc:
            return {"error": str(exc)}
    return check_browser(headless=not headed, target_url=url or None).as_dict()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
