# Leads Discovery & Contact Enrichment Pipeline

Part of **Reachy** by **ISIRA Automations**.

This directory contains autonomous lead discovery datasets, high-throughput contact enrichers, and network verification tools designed to gather verified business phone numbers and inquiry emails.

---

## 📂 Directory Contents

| File | Description |
| :--- | :--- |
| [`contact_enricher.py`](file:///Users/lakshitsinghvi/Documents/Repos/Google-maps-leads/leads/contact_enricher.py) | Multi-source contact extractor implementing Cloudflare XOR cipher decoding, Schema.org JSON-LD parsing, Google Maps authority link extraction, and contact subpage crawling (`/contact`, `/events`). |
| [`philly_venues_1000.json`](file:///Users/lakshitsinghvi/Documents/Repos/Google-maps-leads/leads/philly_venues_1000.json) | Production-grade dataset of verified venue and hospitality leads with resolved direct phone numbers (95%+ match) and verified booking/inquiry emails. |
| [`leads_1000.json`](file:///Users/lakshitsinghvi/Documents/Repos/Google-maps-leads/leads/leads_1000.json) | 1,000 real, deduplicated healthcare/business leads with ratings, review volume, category, and physical address. |
| [`verified_leads.json`](file:///Users/lakshitsinghvi/Documents/Repos/Google-maps-leads/leads/verified_leads.json) | Deep-crawl samples verifying active website accessibility and contact touchpoints. |
| [`verification_audit.json`](file:///Users/lakshitsinghvi/Documents/Repos/Google-maps-leads/leads/verification_audit.json) | Network audit results verifying domain response rates (<5-10% error rate). |
| [`run_1000_leads_audit.py`](file:///Users/lakshitsinghvi/Documents/Repos/Google-maps-leads/leads/run_1000_leads_audit.py) | Standalone concurrent auditing script used to sample and test target websites. |
| [`sample_leads.csv`](file:///Users/lakshitsinghvi/Documents/Repos/Google-maps-leads/leads/sample_leads.csv) | Exported spreadsheet representation of leads ready for CRM/Excel import. |

---

## 🎯 High-Trust Multi-Layer Contact Extraction

Standard scrapers fail on modern websites due to Cloudflare email obfuscation, single-page app (SPA) rendering, and dynamic scripts. `contact_enricher.py` overcomes this with:

1. **Google Maps Place Authority Panes**: Direct extraction of registered business phone numbers (`data-item-id="phone"`) and canonical authority domain links (`data-item-id="authority"`).
2. **Cloudflare XOR Cipher Decoder**: Reverses email protection hex strings (`data-cfemail` and `/cdn-cgi/l/email-protection#<hex>`) into cleartext ASCII emails.
3. **Schema.org JSON-LD Resolution**: Parses `<script type="application/ld+json">` for `LocalBusiness`, `Organization`, and `Restaurant` schema entities for direct telephone and email tags.
4. **Subpage Traversal**: Automatically follows and crawls high-intent contact pages (`/contact`, `/contact-us`, `/private-events`, `/events`, `/about`).
5. **Pattern Normalization**: Formats US phone numbers into standard `+1 (XXX) XXX-XXXX` and filters out generic web assets (`sentry.io`, `wixpress`, `bootstrap`).

---

## 🚀 Running the Contact Enricher

To run enrichment and contact resolution on a lead dataset:

```bash
python3 leads/contact_enricher.py
```

To run network accessibility audits:

```bash
python3 leads/run_1000_leads_audit.py
```
