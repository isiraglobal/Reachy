#!/usr/bin/env python3
"""Multi-Source Contact Discovery & Enrichment Engine for Philadelphia Venues.

Combines trusted sources:
1. Google Maps Authority Links & Direct Business Detail Panes
2. Official Venue Websites (Crawl: Homepage, Contact, Events, Private-Events)
3. Schema.org JSON-LD Structured Data (PostalAddress, Telephone, Email)
4. Cloudflare Email Protection XOR Cipher Decoder (`data-cfemail`)
5. Mailto Links, Tel Anchors, and Business Registry Regex
"""

import json
import logging
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set, Tuple

import bs4
import certifi

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("contact_discovery")

SSL_CTX = ssl.create_default_context(cafile=certifi.where())

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9"
}


def decode_cloudflare_email(cf_hex: str) -> Optional[str]:
    """Decodes email protected with Cloudflare XOR cipher."""
    if not cf_hex or len(cf_hex) < 4:
        return None
    try:
        key = int(cf_hex[:2], 16)
        email = "".join(chr(int(cf_hex[i:i+2], 16) ^ key) for i in range(2, len(cf_hex), 2))
        if "@" in email and "." in email:
            return email.strip()
    except Exception:
        pass
    return None


def clean_phone_number(raw_phone: str) -> Optional[str]:
    """Normalizes phone string to clean US format: +1 (XXX) XXX-XXXX."""
    if not raw_phone:
        return None
    digits = re.sub(r"\D", "", raw_phone)
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10:
        return f"+1 ({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) > 10 and len(digits) <= 12:
        return f"+{digits}"
    return raw_phone.strip() if len(digits) >= 7 else None


def fetch_url_html(url: str, timeout: int = 7) -> str:
    """Fetches raw HTML from a target URL."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def extract_contacts_from_html(html: str, base_url: str) -> Dict[str, Any]:
    """Extracts emails and phone numbers from HTML using trusted multi-pattern analysis."""
    emails: Set[str] = set()
    phones: Set[str] = set()

    # 1. Cloudflare protected emails
    for cf in re.findall(r"data-cfemail=[\"']([a-fA-F0-9]+)[\"']", html):
        decoded = decode_cloudflare_email(cf)
        if decoded:
            emails.add(decoded)

    for cf in re.findall(r"/cdn-cgi/l/email-protection#([a-fA-F0-9]+)", html):
        decoded = decode_cloudflare_email(cf)
        if decoded:
            emails.add(decoded)

    # 2. BeautifulSoup DOM inspection
    soup = bs4.BeautifulSoup(html, "html.parser")

    # Mailto anchors
    for a in soup.select("a[href^='mailto:']"):
        href = a["href"].replace("mailto:", "").split("?")[0].strip()
        if "@" in href:
            emails.add(href)

    # Tel anchors
    for a in soup.select("a[href^='tel:']"):
        href = a["href"].replace("tel:", "").strip()
        cleaned = clean_phone_number(href)
        if cleaned:
            phones.add(cleaned)

    # 3. Schema.org JSON-LD Structured Data (Highly Trusted Source)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            if not script.string:
                continue
            data = json.loads(script.string)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    # Direct telephone & email
                    tel = item.get("telephone") or item.get("phone")
                    if tel:
                        cl_tel = clean_phone_number(str(tel))
                        if cl_tel:
                            phones.add(cl_tel)
                    em = item.get("email")
                    if em and "@" in str(em):
                        emails.add(str(em).strip())
        except Exception:
            pass

    # 4. Visible regex on text content
    text_content = soup.get_text(separator=" ", strip=True)
    raw_emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text_content)
    for e in raw_emails:
        el = e.lower()
        if not any(el.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".svg", ".js", ".css", ".gif", ".woff"]) \
           and not any(bad in el for bad in ["sentry", "wixpress", "cloudflare", "schema", "example", "you@company"]):
            emails.add(e)

    # Phone regex on text content
    raw_phones = re.findall(r"(?:(?:\+?1\s*(?:[.-]\s*)?)?(?:\(\s*([2-9]1[02-9]|[2-9][02-8]1|[2-9][02-8][02-9])\s*\)|([2-9]1[02-9]|[2-9][02-8]1|[2-9][02-8][02-9]))\s*(?:[.-]\s*)?)?([2-9]1[02-9]|[2-9][02-9]1|[2-9][02-9]{2})\s*(?:[.-]\s*)?([0-9]{4})(?:\s*(?:#|x\.?|ext\.?|extension)\s*(\d+))?", text_content)
    for p in raw_phones:
        joined = "".join(p)
        cleaned = clean_phone_number(joined)
        if cleaned:
            phones.add(cleaned)

    return {
        "emails": list(emails),
        "phones": list(phones)
    }


def enrich_venue_contacts(venue: Dict[str, Any]) -> Dict[str, Any]:
    """Crawls the official website and subpages to extract trusted contact points."""
    website = venue.get("website")
    if not website or "google.com" in website:
        return venue

    clean_base = website.split("?")[0].rstrip("/")
    candidate_urls = [
        clean_base,
        f"{clean_base}/contact",
        f"{clean_base}/contact-us",
        f"{clean_base}/events",
        f"{clean_base}/private-events",
        f"{clean_base}/book",
        f"{clean_base}/inquire"
    ]

    all_emails: Set[str] = set(venue.get("all_emails") or [])
    all_phones: Set[str] = set([venue["phone"]] if venue.get("phone") else [])

    for u in candidate_urls:
        html = fetch_url_html(u)
        if html:
            res = extract_contacts_from_html(html, clean_base)
            all_emails.update(res["emails"])
            all_phones.update(res["phones"])
            if all_emails and all_phones:
                break

    venue["all_emails"] = sorted(list(all_emails))
    venue["all_phones"] = sorted(list(all_phones))
    
    if all_emails and not venue.get("email"):
        # Select best representative inquiry email
        best = next((e for e in venue["all_emails"] if any(k in e.lower() for k in ["events", "info", "contact", "sales", "inquir", "book"])), venue["all_emails"][0])
        venue["email"] = best

    if all_phones and not venue.get("phone"):
        venue["phone"] = venue["all_phones"][0]

    return venue


def process_lead_batch(leads: List[Dict[str, Any]], max_workers: int = 12) -> List[Dict[str, Any]]:
    """Runs parallel website enrichment across the lead batch."""
    logger.info(f"[*] Commencing concurrent contact enrichment on {len(leads)} venues (Concurrency: {max_workers})...")
    
    enriched = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(enrich_venue_contacts, dict(v)): v for v in leads}
        completed = 0
        for fut in as_completed(future_map):
            completed += 1
            try:
                res = fut.result()
                enriched.append(res)
                if res.get("email") or res.get("phone"):
                    logger.info(f"[{completed}/{len(leads)}] {res['title']} -> Phone: {res.get('phone')} | Email: {res.get('email')}")
            except Exception as e:
                orig = future_map[fut]
                enriched.append(orig)

    return enriched


def main():
    filepath = os.path.join(os.path.dirname(__file__), "philly_venues_1000.json")
    if not os.path.exists(filepath):
        print(f"Dataset not found at {filepath}")
        return

    with open(filepath, "r", encoding="utf-8") as f:
        venues = json.load(f)

    print(f"Loaded {len(venues)} venues from {filepath}")
    phones = sum(1 for v in venues if v.get("phone"))
    emails = sum(1 for v in venues if v.get("email"))
    print(f"Current Stats -> Venues with Phone: {phones} ({phones/len(venues)*100:.1f}%) | Venues with Email: {emails} ({emails/len(venues)*100:.1f}%)")
    print("Enricher ready. To re-crawl a slice: process_lead_batch(venues[:20])")


if __name__ == "__main__":
    main()

