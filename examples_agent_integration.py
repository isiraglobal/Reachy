"""Integration examples showing how to use google_maps_leads with popular AI agent frameworks."""

# ==============================================================================
# 1. LangChain / LangGraph Tool Integration
# ==============================================================================
def langchain_example():
    """How to bind Google Maps Leads as a tool to any LangChain / LangGraph agent."""
    from langchain.tools import tool
    from google_maps_leads import GoogleMapsScraper

    @tool
    def extract_google_maps_leads(query: str, limit: int = 10, enrich: bool = True) -> list[dict]:
        """Search Google Maps for businesses and extract leads with phone, email, website, and socials.

        Args:
            query: Search query, e.g. 'Coffee roasters in Portland OR' or 'Plumbers in Denver'
            limit: Maximum leads to extract (default 10)
            enrich: Whether to fetch website, emails, and social profiles
        """
        scraper = GoogleMapsScraper(headed=False)
        leads = scraper.scrape_leads(query=query, limit=limit, enrich=enrich)
        return [lead.to_dict() for lead in leads]

    # Usage with an agent:
    # agent = create_react_agent(llm, tools=[extract_google_maps_leads])
    # response = agent.invoke({"messages": [("user", "Find 5 dental clinics in Dallas TX with emails")]})
    return extract_google_maps_leads


# ==============================================================================
# 2. CrewAI Custom Tool Integration
# ==============================================================================
def crewai_example():
    """How to use as a CrewAI BaseTool."""
    from crewai.tools import BaseTool
    from pydantic import BaseModel, Field
    from google_maps_leads import GoogleMapsScraper

    class GoogleMapsLeadsInput(BaseModel):
        query: str = Field(..., description="Google Maps search term (e.g. 'Gyms in Miami')")
        limit: int = Field(5, description="Number of results to extract")

    class GoogleMapsLeadsTool(BaseTool):
        name: str = "Google Maps Leads Tool"
        description: str = "Extracts verified business leads from Google Maps including contact info."
        args_schema: type[BaseModel] = GoogleMapsLeadsInput

        def _run(self, query: str, limit: int = 5) -> str:
            scraper = GoogleMapsScraper(headed=False)
            leads = scraper.scrape_leads(query=query, limit=limit, enrich=True)
            import json
            return json.dumps([l.to_dict() for l in leads], indent=2)

    return GoogleMapsLeadsTool


# ==============================================================================
# 3. Direct Function Calling (OpenAI / Anthropic / Gemini SDKs)
# ==============================================================================
def direct_sdk_tool_definition():
    """Tool specification for direct function calling with OpenAI / Gemini / Anthropic."""
    return {
        "name": "extract_google_maps_leads",
        "description": "Searches Google Maps for businesses and extracts rich lead data (phone, email, website, social handles, address, rating).",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Business search query (e.g. 'Roofing contractors in Austin, TX')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of leads to retrieve (1-50)",
                    "default": 10
                },
                "enrich": {
                    "type": "boolean",
                    "description": "Whether to extract phone, email and socials from the business website",
                    "default": True
                }
            },
            "required": ["query"]
        }
    }


if __name__ == "__main__":
    print("Agent Integration Patterns Ready.")
