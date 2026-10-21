# Leads Pipeline & Verification Data

This directory contains lead generation, deduplication, and verification assets gathered from Google Maps across major US metro markets.

---

## Directory Contents

| File | Description |
| :--- | :--- |
| `leads_1000.json` | 1,000 real, deduplicated business leads with business title, review counts, star ratings, categories, and street addresses. |
| `verified_leads.json` | Deep-crawl samples verifying website accessibility and contact touchpoints. |
| `verification_audit.json` | High-load concurrent curl audit results verifying active domain response rates. |
| `run_1000_leads_audit.py` | Standalone auditing script used to sample and test target websites. |
| `sample_leads.csv` | Exported CSV representation of the dataset for spreadsheet viewing. |
| `run_1000.log` | Raw execution and scrape event log. |

---

## Lead Schema

Each lead in `leads_1000.json` adheres to the following structure:

```json
{
  "title": "Blunn Creek Family Dentistry",
  "category": "Dentist",
  "rating": 4.9,
  "reviews_count": 182,
  "phone": null,
  "website": null,
  "email": null,
  "address": "2550 South Interstate 35 Frontage Road",
  "url": "https://www.google.com/maps/place/...",
  "social_profiles": [],
  "extra_details": {}
}
```

---

## Running Lead Audits

To audit network accessibility on lead batches:

```bash
python3 leads/run_1000_leads_audit.py
```
