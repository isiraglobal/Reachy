# Leads discovery and enrichment (historical)

Part of **Reachy** by **ISIRA Automations**.

This directory contains the original contact-enrichment experiments and historical lead datasets. The production workflow is the `reachy` CLI, which imports these records into SQLite, preserves provenance, deduplicates, and assigns explicit verification states.

## Files

| File | Description |
| :--- | :--- |
| `contact_enricher.py` | Historical multi-source extractor: Cloudflare XOR decoding, Schema.org JSON-LD, Maps authority links, and contact-page crawling. TLS verification is enabled. |
| `philly_venues_1000.json` | Historical venue/hospitality dataset. Treat all contacts as unverified until rechecked by `reachy`. |
| `leads_1000.json` | Historical business/healthcare lead dataset. It has limited contact fields; do not assume emails or phones exist. |
| `verified_leads.json` | Historical deep-crawl sample. "Verified" in the filename reflects the old script's check, not a Reachy verification state. |
| `verification_audit.json` | Historical network audit results. Not a current guarantee. |
| `run_1000_leads_audit.py` | Historical concurrent website audit script. |
| `sample_leads.csv` | Spreadsheet representation for inspection/import. |

## Data caveats

- The datasets are **not** automatically sendable. Reachy verifies each contact and requires an explicit published source before live policy can pass.
- The repository does not claim a specific phone/email match rate. Old percentages were not reproduced under a controlled benchmark and have been removed.
- A published email is not consent. See [docs/COMPLIANCE.md](../docs/COMPLIANCE.md).
- Website structures change; enrichment may return fewer contacts over time.

## Import into Reachy

```bash
reachy import --file leads/philly_venues_1000.json \
  --source legacy_dataset --list philly_venues
reachy list sample --list philly_venues --size 10 --seed 42
```

Inspect results before approving the list:

```bash
reachy leads list --list philly_venues --limit 50
```

## Historical scripts

```bash
python3 leads/contact_enricher.py
python3 leads/run_1000_leads_audit.py
```

These scripts are retained for reference. They do not enforce campaign consent, suppression, or sending policy; use `reachy` for production.
