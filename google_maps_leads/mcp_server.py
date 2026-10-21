"""Model Context Protocol (MCP) Server for Google Maps Leads.

Compatible with Cursor, Claude Desktop, Antigravity, and any MCP client.
Supports both MCP 2.x (`MCPServer`) and fallback to MCP 1.x.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from .models import Lead
from .scraper import GoogleMapsScraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("google_maps_leads_mcp")

try:
    from mcp.server.mcpserver import MCPServer
    server = MCPServer("google-maps-leads")

    @server.tool()
    def extract_google_maps_leads(
        query: str,
        limit: int = 10,
        enrich: bool = True,
        headed: bool = True
    ) -> List[Dict[str, Any]]:
        """Search and extract business leads from Google Maps using autonomous browser automation.

        Args:
            query: The search query, e.g. 'Dentists in Austin, TX' or 'Coffee shops in Seattle'.
            limit: Maximum number of leads to extract (default: 10, max: 50).
            enrich: Whether to automatically enrich phone, email, website and socials (default: True).
            headed: Whether to display the browser window (default: True).

        Returns:
            A list of business lead objects containing title, category, rating, reviews,
            phone, website, email, address, social profiles, and maps URL.
        """
        clamped_limit = min(max(1, limit), 50)
        scraper = GoogleMapsScraper(headed=headed)
        leads = scraper.scrape_leads(query=query, limit=clamped_limit, enrich=enrich)
        return [lead.to_dict() for lead in leads]

    def main():
        server.run()

except ImportError:
    # Fallback to standard Low-Level Server if mcpserver is unavailable
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    import mcp.types as types

    server = Server("google-maps-leads")

    @server.call_tool()
    async def call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
        args = arguments or {}
        if name == "extract_google_maps_leads":
            query = args.get("query", "")
            limit = min(int(args.get("limit", 10)), 50)
            enrich = bool(args.get("enrich", True))
            headed = bool(args.get("headed", True))

            def _run():
                scraper = GoogleMapsScraper(headed=headed)
                return scraper.scrape_leads(query=query, limit=limit, enrich=enrich)

            loop = asyncio.get_running_loop()
            leads = await loop.run_in_executor(None, _run)
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps([l.to_dict() for l in leads], indent=2, ensure_ascii=False)
                )
            ]
        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

    async def _async_main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    def main():
        asyncio.run(_async_main())


if __name__ == "__main__":
    main()
