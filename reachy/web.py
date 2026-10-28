"""Safe website contact extraction (TLS verified, no challenge bypass)."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import ssl
import urllib.parse
import urllib.request
from typing import Any, Optional

import bs4
import certifi

from .normalize import clean_text, is_valid_email_syntax, normalize_email, normalize_phone

SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
USER_AGENT = "Reachy/2.0 (+https://github.com/isiraglobal/Reachy)"
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
CONTACT_PATHS = ("", "/contact", "/contact-us", "/about", "/events", "/private-events", "/book", "/inquire")
BAD_EMAIL_PARTS = ("sentry", "wixpress", "cloudflare", "schema", "example.com", "you@company")
BAD_EMAIL_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".svg", ".js", ".css", ".gif", ".woff")


def decode_cloudflare_email(value: str) -> Optional[str]:
    if not value or len(value) < 4:
        return None
    try:
        key = int(value[:2], 16)
        email = "".join(chr(int(value[i : i + 2], 16) ^ key) for i in range(2, len(value), 2))
        return email if "@" in email and "." in email else None
    except (ValueError, IndexError):
        return None


def validate_public_url(url: str) -> str:
    """Reject non-HTTP URLs and literal private/loopback/link-local targets.

    This is a best-effort SSRF guard for agent-facing tools. It resolves the
    hostname before the request; a hostile DNS server could still rebind later.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must use http or https")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("URL must include a public hostname and no credentials")
    host = parsed.hostname.lower().strip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("URL host is not public")
    candidates: list[str] = []
    try:
        candidates.append(str(ipaddress.ip_address(host)))
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        except OSError as exc:
            raise ValueError(f"URL host could not be resolved: {exc}") from exc
        for info in infos:
            candidates.append(str(info[4][0]))
    for candidate in candidates:
        address = ipaddress.ip_address(candidate)
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise ValueError("URL resolves to a non-public address")
    return url


def fetch_html(url: str, timeout: float = 10.0, max_bytes: int = 2_000_000) -> tuple[str, str]:
    validate_public_url(url)
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    )
    with urllib.request.urlopen(request, context=SSL_CONTEXT, timeout=timeout) as response:
        payload = response.read(max_bytes)
        return payload.decode("utf-8", errors="ignore"), response.geturl()


def extract_contacts_from_html(html: str, base_url: str = "") -> dict[str, Any]:
    emails: set[str] = set()
    phones: set[str] = set()
    socials: set[str] = set()
    json_ld_types: list[str] = []

    for value in re.findall(r"data-cfemail=[\"']([a-fA-F0-9]+)[\"']", html):
        decoded = decode_cloudflare_email(value)
        if decoded:
            emails.add(normalize_email(decoded))
    for value in re.findall(r"/cdn-cgi/l/email-protection#([a-fA-F0-9]+)", html):
        decoded = decode_cloudflare_email(value)
        if decoded:
            emails.add(normalize_email(decoded))

    soup = bs4.BeautifulSoup(html, "html.parser")
    for anchor in soup.select("a[href^='mailto:']"):
        candidate = normalize_email(anchor.get("href", ""))
        if is_valid_email_syntax(candidate):
            emails.add(candidate)
    for anchor in soup.select("a[href^='tel:']"):
        phone = normalize_phone(anchor.get("href", "").replace("tel:", ""))
        if phone:
            phones.add(phone)
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        if any(domain in href for domain in ("facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com")):
            socials.add(href)

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if not isinstance(item, dict):
                continue
            json_ld_types.append(str(item.get("@type") or "").strip())
            email = item.get("email")
            if email and is_valid_email_syntax(str(email).replace("mailto:", "")):
                emails.add(normalize_email(str(email)))
            phone = item.get("telephone") or item.get("phone")
            if phone:
                normalized = normalize_phone(phone)
                if normalized:
                    phones.add(normalized)

    text = soup.get_text(" ", strip=True)
    for candidate in EMAIL_RE.findall(text):
        lowered = candidate.lower()
        if any(lowered.endswith(ext) for ext in BAD_EMAIL_EXTENSIONS):
            continue
        if any(bad in lowered for bad in BAD_EMAIL_PARTS):
            continue
        if is_valid_email_syntax(candidate):
            emails.add(normalize_email(candidate))

    return {
        "emails": sorted(emails),
        "phones": sorted(phones),
        "socials": sorted(socials),
        "json_ld_types": sorted({value for value in json_ld_types if value}),
        "base_url": base_url,
    }


def crawl_contact_pages(website: str, timeout: float = 10.0) -> dict[str, Any]:
    """Crawl a bounded set of contact-oriented pages on a business site."""
    parsed = urllib.parse.urlparse(website)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"emails": [], "phones": [], "pages": [], "errors": []}
    base = f"{parsed.scheme}://{parsed.netloc}"
    emails: set[str] = set()
    phones: set[str] = set()
    pages: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in CONTACT_PATHS:
        url = base + path
        try:
            html, final_url = fetch_html(url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            errors.append({"url": url, "error": exc.__class__.__name__})
            continue
        found = extract_contacts_from_html(html, final_url)
        emails.update(found["emails"])
        phones.update(found["phones"])
        pages.append({"url": final_url, "emails": found["emails"], "phones": found["phones"]})
    return {"emails": sorted(emails), "phones": sorted(phones), "pages": pages, "errors": errors}
