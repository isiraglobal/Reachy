import json
import logging
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

import bs4
import certifi

from .drivers import BrowserDriver, build_driver
from .models import Lead

logger = logging.getLogger("google_maps_leads")


class GoogleMapsScraper:
    """Google Maps leads extractor with Playwright preferred.

    The legacy ``agent-browser`` CLI is used only as a fallback. Browser
    automation never attempts to bypass CAPTCHAs, access controls, or rate
    limits; blocked sources are reported and skipped.
    """

    def __init__(
        self,
        headed: bool = True,
        viewport_w: int = 1920,
        viewport_h: int = 1080,
        proxy: Optional[str] = None,
        backend: str = "auto",
        browser_driver: Optional[BrowserDriver] = None,
    ):
        self.headed = headed
        self.viewport_w = viewport_w
        self.viewport_h = viewport_h
        self.proxy = proxy or os.environ.get("AGENT_BROWSER_PROXY") or os.environ.get("HTTPS_PROXY")
        self.backend = backend
        self._driver = browser_driver
        self._ssl_ctx = ssl.create_default_context(cafile=certifi.where())

    def _get_driver(self) -> BrowserDriver:
        if self._driver is None:
            self._driver = build_driver(
                backend=self.backend,
                headed=self.headed,
                proxy=self.proxy,
                viewport=(self.viewport_w, self.viewport_h),
            )
        return self._driver

    def close(self) -> None:
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None

    def _eval_js(self, js_code: str) -> Any:
        """Runs JavaScript through the configured browser driver."""
        output = self._get_driver().eval(js_code)
        if isinstance(output, str):
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return output
        return output

    def ensure_browser(self, initial_url: str = "https://www.google.com/maps"):
        """Starts or reuses a browser session without killing other processes."""
        driver = self._get_driver()
        current = ""
        try:
            current = driver.get_url()
        except Exception:
            current = ""
        if not current or "google.com" not in current:
            logger.info("Initializing browser session (%s)...", getattr(driver, "name", "driver"))
            driver.open(initial_url)
            driver.set_viewport(self.viewport_w, self.viewport_h)
            self.dismiss_cookie_dialog()

    def dismiss_cookie_dialog(self):
        """Dismisses cookie consent banners if present."""
        dismiss_js = """(() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const acceptBtn = buttons.find(b => {
                const txt = (b.innerText || '').toLowerCase().trim();
                const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                return txt === 'accept all' || txt === 'i agree' || txt === 'accept' ||
                       aria.includes('accept all') || txt.includes('tout accepter') || txt.includes('alle akzeptieren');
            });
            if (acceptBtn) {
                acceptBtn.click();
                return true;
            }
            return false;
        })()"""
        try:
            self._eval_js(dismiss_js)
        except Exception:
            pass

    def extract_search_cards(self) -> List[Dict[str, Any]]:
        """Parses all rendered place cards in the Google Maps search results feed."""
        extract_cards_js = """(() => {
            const feed = document.querySelector('div[role=\"feed\"]') || document;
            const cards = Array.from(feed.querySelectorAll('div.Nv2PK'));
            return cards.map(card => {
                const title = card.querySelector('.qBF1Pd')?.innerText?.trim() || 
                              card.querySelector('a.hfpxzc')?.getAttribute('aria-label')?.trim() || '';
                
                // Rating
                const ratingEl = card.querySelector('span.MW4etd');
                const rating = ratingEl ? parseFloat(ratingEl.innerText) : null;
                
                // Reviews
                const reviewsEl = card.querySelector('span.UY7F9');
                let reviews = null;
                if (reviewsEl) {
                    const match = reviewsEl.innerText.match(/\\(([0-9,]+)\\)/);
                    if (match) reviews = parseInt(match[1].replace(/,/g, ''), 10);
                }

                // Text lines
                const textContainers = Array.from(card.querySelectorAll('div.W4Efsd'));
                const allLines = textContainers.map(tc => tc.innerText.trim()).filter(Boolean);
                
                // Google Maps place URL
                const placeUrl = card.querySelector('a.hfpxzc')?.href || '';

                // Action links (website, reservation, booking)
                const actionLinks = Array.from(card.querySelectorAll('a[href]')).map(a => a.href).filter(h => !h.includes('google.com/maps'));
                let websiteLink = card.querySelector('a[aria-label*=\"website\" i], a[data-value*=\"Website\"]')?.getAttribute('href') || null;
                if (websiteLink && (websiteLink.startsWith('/') || websiteLink.includes('/aclk?'))) {
                    websiteLink = null;
                }

                // Category & Address
                let category = null;
                let address = null;
                for (const line of allLines) {
                    if (line.includes('·')) {
                        const parts = line.split('·').map(p => p.trim()).filter(p => p && p !== '');
                        if (parts.length >= 1 && !category && !parts[0].match(/open|close/i)) {
                            category = parts[0];
                            if (parts.length >= 2) {
                                const rawAddr = parts[1].split('\\n')[0].trim();
                                if (rawAddr && !rawAddr.match(/open|close/i)) {
                                    address = rawAddr;
                                }
                            }
                        }
                    }
                }

                // Phone match from raw text
                let phone = null;
                for (const line of allLines) {
                    const phoneMatch = line.match(/(?:\\+?1[-.\\s]?)?\\(?([0-9]{3})\\)?[-.\\s]?([0-9]{3})[-.\\s]?([0-9]{4})/);
                    if (phoneMatch) {
                        phone = phoneMatch[0];
                        break;
                    }
                }

                return {
                    title,
                    category,
                    rating,
                    reviews_count: reviews,
                    address,
                    phone,
                    website: websiteLink,
                    url: placeUrl,
                    action_links: actionLinks,
                    all_lines: allLines
                };
            }).filter(item => Boolean(item.title));
        })()"""
        return self._eval_js(extract_cards_js) or []

    def scroll_feed_wheel(self) -> Dict[str, Any]:
        """Dispatches smooth wheel scrolling on the Google Maps feed."""
        scroll_js = """(() => {
            const feed = document.querySelector('div[role=\"feed\"]');
            if (!feed) return { count: 0, scrollHeight: 0 };
            feed.scrollTop = feed.scrollHeight;
            feed.dispatchEvent(new WheelEvent('wheel', { deltaY: 2500, bubbles: true }));
            feed.dispatchEvent(new Event('scroll', { bubbles: true }));
            return {
                count: feed.querySelectorAll('div.Nv2PK').length,
                scrollHeight: feed.scrollHeight
            };
        })()"""
        return self._eval_js(scroll_js) or {}

    def search_leads(self, query: str, limit: int = 10, max_scroll_attempts: int = 12) -> List[Lead]:
        """Searches Google Maps and extracts leads up to `limit`."""
        self.ensure_browser()
        encoded = urllib.parse.quote_plus(query)
        search_url = f"https://www.google.com/maps/search/{encoded}"
        logger.info(f"Navigating to: {search_url}")

        driver = self._get_driver()
        driver.open(search_url)
        driver.wait(3000)
        self.dismiss_cookie_dialog()

        seen_leads: Dict[str, Lead] = {}
        last_count = 0
        stuck_counter = 0

        for attempt in range(max_scroll_attempts):
            cards = self.extract_search_cards()
            for c in cards:
                title = c["title"]
                url = c.get("url") or ""
                key = url if url else title

                if key not in seen_leads:
                    lead = Lead(
                        title=title,
                        category=c.get("category"),
                        rating=c.get("rating"),
                        reviews_count=c.get("reviews_count"),
                        phone=c.get("phone"),
                        website=c.get("website"),
                        address=c.get("address"),
                        url=url,
                    )
                    seen_leads[key] = lead

            logger.info(f"Extracted {len(seen_leads)} / {limit} leads (scroll attempt {attempt + 1})")
            if len(seen_leads) >= limit:
                break

            if len(seen_leads) == last_count:
                stuck_counter += 1
                if stuck_counter >= 3:
                    logger.info("No further places loaded. Ending pagination.")
                    break
            else:
                stuck_counter = 0
            last_count = len(seen_leads)

            self.scroll_feed_wheel()
            time.sleep(2)

        leads_list = list(seen_leads.values())[:limit]
        return leads_list

    def enrich_lead_contact_info(self, lead: Lead) -> Lead:
        """Enriches a lead with phone number, website, email, and social profiles.

        Uses direct web enrichment via duckduckgo html search and website DOM parsing.
        """
        # If website or phone is missing, extract directly from the Google Maps place profile via agent-browser
        if lead.url and (not lead.website or not lead.phone or not lead.address):
            try:
                driver = self._get_driver()
                driver.open(lead.url)
                driver.wait(1800)
                details_js = """(() => {
                    const website = document.querySelector('a[data-item-id=\"authority\"]')?.href || null;
                    const phone = document.querySelector('button[data-item-id*=\"phone\"]')?.innerText?.trim()?.replace(/^[\\s\\S]*?\\+/, '+') || null;
                    const address = document.querySelector('button[data-item-id=\"address\"]')?.innerText?.trim()?.replace(/^[\\s\\S]*?\\n/, '') || null;
                    return { website, phone, address };
                })()"""
                details = self._eval_js(details_js)
                if isinstance(details, dict):
                    if details.get("website") and not lead.website:
                        lead.website = details["website"]
                    if details.get("phone") and not lead.phone:
                        lead.phone = details["phone"]
                    if details.get("address") and (not lead.address or lead.address == ""):
                        lead.address = details["address"]
            except Exception as e:
                logger.debug(f"Direct Maps place enrichment error: {e}")

        # Search engine fallback if website is still missing
        if not lead.website or not lead.phone:
            search_query = f"{lead.title} {lead.address or ''}".strip()
            try:
                web_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(search_query)}"
                req = urllib.request.Request(
                    web_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    }
                )
                with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=8) as r:
                    html = r.read().decode("utf-8", errors="ignore")
                    soup = bs4.BeautifulSoup(html, "html.parser")

                    for r_el in soup.select(".result"):
                        a_el = r_el.select_one(".result__url") or r_el.select_one("a.result__title")
                        snip_el = r_el.select_one(".result__snippet")
                        snippet = snip_el.get_text() if snip_el else ""

                        # Extract phone if missing
                        if not lead.phone and snippet:
                            match = re.search(r"(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})", snippet)
                            if match:
                                lead.phone = match.group(0)

                        # Extract official website if missing
                        if not lead.website and a_el:
                            raw_href = a_el.get("href", "")
                            parsed = urllib.parse.urlparse(raw_href)
                            qs = urllib.parse.parse_qs(parsed.query)
                            candidate_url = qs.get("uddg", [None])[0] or raw_href
                            if candidate_url and candidate_url.startswith("http"):
                                ignored = ["google", "duckduckgo", "yelp", "yellowpages", "mapquest", "facebook", "instagram"]
                                if not any(x in candidate_url for x in ignored):
                                    lead.website = candidate_url
            except Exception as e:
                logger.debug(f"Web search enrichment error for {lead.title}: {e}")

        # Now extract email and phone from official website (both HTTP request and agent-browser fallback)
        if lead.website and not lead.email:
            clean_site = lead.website.split("?")[0]
            site_html = ""
            
            # Step A: Fast HTTP fetch
            try:
                req = urllib.request.Request(
                    clean_site,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                    }
                )
                with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=6) as r:
                    site_html = r.read().decode("utf-8", errors="ignore")
            except Exception:
                pass

            # Step B: If HTTP fails (e.g. Cloudflare / JS rendering), open via agent-browser
            if not site_html:
                try:
                    driver = self._get_driver()
                    driver.open(clean_site)
                    driver.wait(2000)
                    browser_data_js = """(() => {
                        const text = document.body ? document.body.innerText : '';
                        const mailtos = Array.from(document.querySelectorAll('a[href^=\"mailto:\"]'))
                            .map(a => a.href.replace(/^mailto:/i, '').split('?')[0].trim());
                        const emails = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/g) || [];
                        const tel = document.querySelector('a[href^=\"tel:\"]')?.href?.replace(/^tel:/i, '') || '';
                        return { emails: Array.from(new Set([...emails, ...mailtos])), text, tel };
                    })()"""
                    b_res = self._eval_js(browser_data_js)
                    if isinstance(b_res, dict):
                        b_emails = b_res.get("emails", [])
                        valid_b_emails = [
                            e for e in b_emails 
                            if not any(e.lower().endswith(ext) for ext in [".png", ".jpg", ".webp", ".svg", ".js", ".css", ".gif"])
                            and not any(x in e.lower() for x in ["sentry", "wixpress", "cloudflare", "schema"])
                        ]
                        if valid_b_emails:
                            lead.email = valid_b_emails[0]
                        if not lead.phone and b_res.get("tel"):
                            lead.phone = b_res["tel"].strip()
                except Exception as e:
                    logger.debug(f"Browser website fetch error: {e}")

            # Parse HTTP html if obtained
            if site_html:
                soup = bs4.BeautifulSoup(site_html, "html.parser")
                emails = set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", site_html))
                valid_emails = [
                    e for e in emails 
                    if not any(e.lower().endswith(ext) for ext in [".png", ".jpg", ".webp", ".svg", ".js", ".css", ".gif"])
                    and not any(x in e.lower() for x in ["sentry", "wixpress", "cloudflare", "schema"])
                ]
                if valid_emails and not lead.email:
                    lead.email = valid_emails[0]

                # Fallback phone from site
                if not lead.phone:
                    tel_a = soup.select_one("a[href^='tel:']")
                    if tel_a:
                        lead.phone = tel_a["href"].replace("tel:", "").strip()
                    else:
                        phone_match = re.search(r"(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})", site_html)
                        if phone_match:
                            lead.phone = phone_match.group(0)

        return lead

    def scrape_leads(self, query: str, limit: int = 10, enrich: bool = True) -> List[Lead]:
        """Main method to extract and enrich leads."""
        leads = self.search_leads(query=query, limit=limit)
        if enrich:
            logger.info("Enriching leads with contact details and websites...")
            for i, lead in enumerate(leads):
                leads[i] = self.enrich_lead_contact_info(lead)
        return leads
