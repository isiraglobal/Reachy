# Reachy Repository Audit

> Historical record of the pre-remediation state. The current architecture and controls are documented in the README, AGENTS.md, and the other files in `docs/`. This audit is retained for traceability; do not treat its defect list as the current state.

Date: 2026-10-23
Commit audited: `e77ac7a`

## 1. Current architecture

| Area | Location | Reality |
| :--- | :--- | :--- |
| Maps scraping | `google_maps_leads/scraper.py` | DOM selectors driven through an external `agent-browser` CLI. No Playwright. Removes all `agent-browser` processes via `pkill -f` before every session. |
| Models | `google_maps_leads/models.py` | One flat `Lead` dataclass. No source timestamps, verification state, provenance, or dedupe key. |
| CLI | `google_maps_leads/cli.py` | `reachy-leads` scrape/export. |
| MCP | `google_maps_leads/mcp_server.py` | One scrape tool. Import path works on the installed `mcp` build but relies on an undocumented module layout. |
| Browser diagnostics | `google_maps_leads/browser_test.py`, `browser_installer.py` | Verify the external `agent-browser` binary. `pkill` on every run. No Playwright binary/version/system-dependency check. |
| Contact enrichment | `leads/contact_enricher.py` | Cloudflare XOR + JSON-LD + mailto/tel parsing. **Disables TLS verification** (`CERT_NONE`). No verification, provenance, or dedupe. |
| Outreach | `email_outreach/cold_email_engine.py` | A reporting/simulation script, not a sender. It only writes `QUEUED_FOR_DISPATCH` rows and a JSON report. |
| Config | `email_outreach/inboxes.json` | Five hard-coded, unverified sender identities/domains. No OAuth, secrets, or authorization state. |
| Data | `leads/*.json` | `leads_1000.json` has 1,000 rows but **no emails, phones, or websites**; `philly_venues_1000.json` contains 258 rows despite its name; no per-field source/timestamp. |
| Tests | none | No automated tests, fixtures, or CI. |
| Packaging | `pyproject.toml` | Declares `beautifulsoup4`, `certifi`, `mcp`. Missing runtime imports `dns.resolver` and `rich` used by the outreach script. No optional extras. No `LICENSE` file despite declaring MIT. |

## 2. Defects and unsafe production paths

1. **`NameError` in live code**: `email_outreach/cold_email_engine.py:318` uses `urlparse` without importing it.
2. **Sending is not implemented**: no SMTP/Gmail submission, no queue, retries, idempotency, reconciliation, or audit trail.
3. **Unverified senders**: `inboxes.json` contains domains the repository owner is unlikely to control; using them would be impersonation. No OAuth authorization exists.
4. **Missing dependency declarations**: `dns.resolver` and `rich` are absent from `pyproject.toml`.
5. **TLS verification disabled** in `leads/contact_enricher.py:33-35`, enabling machine-in-the-middle contact harvesting.
6. **Global process killing**: `pkill -f agent-browser` in `scraper.py:78` and `browser_test.py:71` can terminate unrelated user sessions.
7. **No consent/compliance gate**: the current engine has no suppression list, unsubscribe, jurisdiction, source, verification, or provider policy checks.
8. **Unsupported claims**: `6.5X deliverability`, `>95% phone resolution`, and `verified` labels are not backed by reproducible measurements in the repository. They must not be repeated as product guarantees.
9. **No deduplication across sessions**: only in-memory URL/title keys during one scrape.
10. **No durable state**: everything is JSON files and stdout; no restart recovery, migrations, backups, or concurrency safety.
11. **PII/secrets hygiene**: no redaction, encryption, least-privilege OAuth, or account disconnect flow.
12. **Fragile import path** in `mcp_server.py` for `MCPServer` (non-public module).
13. **No licence audit**: dependencies are not pinned or licence-classified; no third-party notices.
14. **No sample QC enforcement**: the 10-row gate is informational only and never blocks anything because nothing sends.

## 3. Reuse decisions

Keep and reuse:

- Google Maps DOM extraction logic and selectors.
- Contact extraction patterns (Cloudflare XOR, JSON-LD, mailto/tel, subpages).
- CLI names `reachy-leads`, `reachy-mcp`, `reachy-browser-test`, `reachy-browser-install`.
- Existing lead datasets (imported into SQLite without modification; originals retained).
- MCP tool surface, extended with the new workflow.

Replace or isolate:

- `agent-browser`-only automation is placed behind a driver interface; Playwright is the preferred supported backend.
- The outreach simulation remains available as a legacy report generator but is explicitly labelled non-sending. Real delivery moves to `reachy`.
- `inboxes.json` demo identities are moved to `inboxes.example.json`; the active file is emptied so no accidental send occurs.

## 4. What is not claimed

- Reachy does not bypass CAPTCHAs, access controls, rate limits, or site restrictions.
- Reachy does not claim inbox placement or "delivered" status without provider events.
- Reachy does not verify mailbox existence unless an explicitly enabled SMTP probe succeeds; without that, addresses are `valid` (published + deliverable domain) or `unknown`/`unverified`, never "guessed and verified".
- Gmail use is subject to Google API terms, OAuth verification, and per-account quotas. Customers must configure their own Google Cloud OAuth client.
