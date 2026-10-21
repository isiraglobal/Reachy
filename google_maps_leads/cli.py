import argparse
import csv
import json
import logging
import sys
from typing import List

from .models import Lead
from .scraper import GoogleMapsScraper


def export_leads_to_csv(leads: List[Lead], filepath: str):
    """Exports extracted leads to a CSV file."""
    if not leads:
        return
    fieldnames = [
        "title",
        "category",
        "rating",
        "reviews_count",
        "phone",
        "website",
        "email",
        "address",
        "social_profiles",
        "url",
    ]
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for lead in leads:
            d = lead.to_dict()
            if isinstance(d.get("social_profiles"), list):
                d["social_profiles"] = " | ".join(d["social_profiles"])
            writer.writerow(d)


def main():
    parser = argparse.ArgumentParser(
        description="Google Maps Leads Extractor & Enrichment Tool (Agent-Browser powered)"
    )
    parser.add_argument("query", type=str, help="Search query (e.g., 'Dentists in Austin, TX')")
    parser.add_argument("-l", "--limit", type=int, default=10, help="Maximum number of leads to extract (default: 10)")
    parser.add_argument("-o", "--output", type=str, default=None, help="Output file path (.json or .csv)")
    parser.add_argument("--headed", action="store_true", default=True, help="Run browser in headed mode (default: True)")
    parser.add_argument("--headless", action="store_false", dest="headed", help="Run browser in headless mode")
    parser.add_argument("--no-enrich", action="store_false", dest="enrich", default=True, help="Skip contact & social enrichment")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    scraper = GoogleMapsScraper(headed=args.headed)
    print(f"[*] Extracting leads for '{args.query}' (limit={args.limit}, enrich={args.enrich})...", file=sys.stderr)
    leads = scraper.scrape_leads(args.query, limit=args.limit, enrich=args.enrich)

    lead_dicts = [lead.to_dict() for lead in leads]

    if args.output:
        if args.output.endswith(".csv"):
            export_leads_to_csv(leads, args.output)
            print(f"[✓] Saved {len(leads)} leads to CSV: {args.output}", file=sys.stderr)
        else:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(lead_dicts, f, indent=2, ensure_ascii=False)
            print(f"[✓] Saved {len(leads)} leads to JSON: {args.output}", file=sys.stderr)
    else:
        print(json.dumps(lead_dicts, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
