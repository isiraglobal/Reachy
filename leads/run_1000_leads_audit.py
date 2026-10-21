import asyncio
import csv
import json
import logging
import random
import re
import ssl
import subprocess
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Set

import certifi

from google_maps_leads.models import Lead
from google_maps_leads.scraper import GoogleMapsScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("batch_fetcher")

# Major cities/metro areas across the US for robust 1000-lead retrieval
TARGET_LOCATIONS = [
    # Texas
    "Austin TX", "Houston TX", "Dallas TX", "San Antonio TX", "Fort Worth TX",
    "El Paso TX", "Arlington TX", "Plano TX", "Round Rock TX", "Frisco TX",
    # California
    "Los Angeles CA", "San Diego CA", "San Jose CA", "San Francisco CA", "Sacramento CA",
    "Fresno CA", "Long Beach CA", "Oakland CA", "Bakersfield CA", "Anaheim CA",
    # Florida
    "Miami FL", "Orlando FL", "Tampa FL", "Jacksonville FL", "St Petersburg FL",
    "Fort Lauderdale FL", "Tallahassee FL", "Cape Coral FL",
    # New York & East
    "New York NY", "Brooklyn NY", "Queens NY", "Buffalo NY", "Rochester NY",
    "Philadelphia PA", "Pittsburgh PA", "Boston MA", "Atlanta GA", "Charlotte NC",
    # Midwest & Central
    "Chicago IL", "Indianapolis IN", "Columbus OH", "Detroit MI", "Nashville TN",
    "Memphis TN", "Louisville KY", "Milwaukee WI", "Minneapolis MN", "Kansas City MO",
    # West & Southwest
    "Phoenix AZ", "Tucson AZ", "Denver CO", "Las Vegas NV", "Seattle WA",
    "Portland OR", "Salt Lake City UT", "Albuquerque NM"
]


def fetch_1000_leads(
    category_query: str = "Dentists",
    target_count: int = 1000,
    output_file: str = "leads_1000.json"
) -> List[Lead]:
    """Fetches up to `target_count` unique leads by iterating over sub-queries."""
    scraper = GoogleMapsScraper(headed=True)
    scraper.ensure_browser()

    all_leads: Dict[str, Lead] = {}
    location_idx = 0

    logger.info(f"[*] Commencing 1000-lead batch fetch for category: '{category_query}'...")

    while len(all_leads) < target_count and location_idx < len(TARGET_LOCATIONS):
        loc = TARGET_LOCATIONS[location_idx]
        location_idx += 1
        query = f"{category_query} in {loc}"
        logger.info(f"--> [{len(all_leads)}/{target_count}] Searching: '{query}'")

        try:
            # We fetch up to 35 leads per city with max scrolling, skipping per-lead deep website enrichment
            # during batch scraping to maximize throughput and prevent rate-limiting.
            leads = scraper.search_leads(query=query, limit=35, max_scroll_attempts=8)
            initial_count = len(all_leads)
            for lead in leads:
                key = lead.url or f"{lead.title}_{lead.address}"
                if key not in all_leads:
                    all_leads[key] = lead
            new_added = len(all_leads) - initial_count
            logger.info(f"    Added {new_added} unique leads from {loc} (Total accumulated: {len(all_leads)})")
        except Exception as e:
            logger.warning(f"Error fetching for '{query}': {e}")
            time.sleep(2)

        # Periodically dump to disk for safety
        if len(all_leads) % 100 < 35 or len(all_leads) >= target_count:
            data = [l.to_dict() for l in all_leads.values()]
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"[Progress Saved] {len(all_leads)} leads written to {output_file}")

    result_leads = list(all_leads.values())[:target_count]
    return result_leads


def curl_test_lead(lead: Dict[str, Any], timeout: int = 6) -> Dict[str, Any]:
    """Tests if a lead actually exists by curl testing its website or maps place URL.

    Under heavy concurrent load, checks HTTP status codes, redirects, and connectivity.
    """
    title = lead.get("title", "")
    website = lead.get("website")
    maps_url = lead.get("url")

    target_url = website if (website and website.startswith("http")) else maps_url

    if not target_url:
        return {
            "title": title,
            "url": "none",
            "exists": False,
            "status_code": 0,
            "error": "No URL found"
        }

    # Execute curl with fast connection timeout and redirect follow
    cmd = [
        "curl", "-s", "-o", "/dev/null",
        "-w", "%{http_code}|%{time_total}",
        "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "-L", "--max-time", str(timeout),
        target_url
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
        out = res.stdout.strip()
        if "|" in out:
            code_str, duration = out.split("|", 1)
            code = int(code_str) if code_str.isdigit() else 0
            # HTTP 200, 301, 302, 403 (Cloudflare/bot protection on live site) indicate real active server
            exists = (200 <= code < 400) or code in [403, 401]
            return {
                "title": title,
                "url": target_url,
                "status_code": code,
                "duration": duration,
                "exists": exists,
                "error": None if exists else f"HTTP status {code}"
            }
        else:
            return {
                "title": title,
                "url": target_url,
                "status_code": 0,
                "exists": False,
                "error": "Curl output empty"
            }
    except Exception as e:
        return {
            "title": title,
            "url": target_url,
            "status_code": 0,
            "exists": False,
            "error": str(e)
        }


def run_batch_and_verification(total_leads_goal: int = 1000, sample_size: int = 20):
    output_json = "leads_1000.json"
    leads = fetch_1000_leads(
        category_query="Dentists",
        target_count=total_leads_goal,
        output_file=output_json
    )

    print(f"\n=======================================================")
    print(f"[✓] Successfully gathered {len(leads)} leads into {output_json}!")
    print(f"=======================================================\n")

    # Pick 10-20 random leads for verification
    actual_sample_size = min(sample_size, len(leads))
    sampled_leads = random.sample([l.to_dict() for l in leads], actual_sample_size)

    print(f"[*] Running heavy concurrent curl verification on {actual_sample_size} random sampled leads...")

    verification_results = []
    # Test under heavy concurrent load (8 parallel workers)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(curl_test_lead, sampled_leads))
        verification_results.extend(results)

    passed = sum(1 for r in verification_results if r["exists"])
    failed = len(verification_results) - passed
    error_rate = (failed / len(verification_results)) * 100 if verification_results else 0.0

    print(f"\n--- VERIFICATION AUDIT RESULTS ---")
    print(f"Total Sampled: {len(verification_results)}")
    print(f"Verified Active: {passed}")
    print(f"Failed / Inactive: {failed}")
    print(f"Error Rate: {error_rate:.2f}% (Target: 5% - 10%)")
    print("----------------------------------\n")

    for i, r in enumerate(verification_results, 1):
        status = "PASSED" if r["exists"] else "FAILED"
        print(f"[{i:02d}] [{status}] {r['title'][:32]:<32} | Code: {r['status_code']} | Time: {r.get('duration','-')}s | {r['url'][:45]}")

    audit_summary = {
        "total_gathered": len(leads),
        "sample_verified": len(verification_results),
        "passed": passed,
        "failed": failed,
        "error_rate_pct": error_rate,
        "results": verification_results
    }
    with open("verification_audit.json", "w", encoding="utf-8") as f:
        json.dump(audit_summary, f, indent=2)
    print(f"\n[✓] Audit written to verification_audit.json")


if __name__ == "__main__":
    run_batch_and_verification()
