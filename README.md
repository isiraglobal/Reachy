# Reachy

Reachy is a self-hosted B2B prospecting and outreach application by **ISIRA Automations**. It keeps lead discovery, contact enrichment, list QA, sending, replies, and audit history in one local SQLite-backed product. You run it on your own machine or VPS; there is no mandatory third-party outreach platform.

Reachy is built to be conservative:

- Nothing sends until a campaign is explicitly approved and started.
- Every live message must pass a compliance gate; unknown or failed checks block the send.
- Addresses are never guessed or marked verified without evidence.
- Inbox placement and "delivered" status are not claimed without provider evidence.
- CAPTCHAs, access controls, rate limits, and site restrictions are not bypassed.

See [docs/AUDIT.md](docs/AUDIT.md) for the original audit and [docs/PLAN.md](docs/PLAN.md) for the implementation plan.

## What it does

| Area | Capability |
| :--- | :--- |
| Lead discovery | Browser-assisted Google Maps extraction through Playwright, with an `agent-browser` fallback. |
| Contact enrichment | Cloudflare XOR decoding, JSON-LD parsing, mailto/tel extraction, and public contact-page crawling. |
| Data quality | Business/contact dedupe, provenance, source URLs, verification states, ICP scoring, conflict flags. |
| List QA | Seeded 10-record sample, persisted review decisions, configurable failure threshold, approval gate. |
| Compliance | Global suppression, unsubscribe/complaint precedence, jurisdiction and lawful-basis checks, sender identity checks. |
| Sending | Mock, SMTP, and Gmail API providers. Test-recipient and dry-run modes. Per-account daily limits. |
| Reliability | Durable message planning, idempotency keys, atomic claims, uncertain-send reconciliation by Message-ID. |
| Replies | IMAP/Gmail sync, dedupe, classification, follow-up cancellation, suppression, human-reviewed drafts. |
| Operations | Sender health, auto-pause, audit log, export, backup/restore, browser diagnostics, CLI JSON output. |
| Automation | MCP stdio server for lead extraction and browser diagnostics. |

## Install

Requires Python 3.10+.

```bash
git clone https://github.com/isiraglobal/Reachy.git
cd Reachy
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[browser,gmail]"
python -m playwright install chromium
cp .env.example .env
reachy init
reachy doctor
```

On Linux, if Chromium system libraries are missing:

```bash
sudo python -m playwright install --with-deps chromium
```

Without the `gmail` extra, SMTP and browser discovery still work. Without the `browser` extra, browser discovery and browser diagnostics are unavailable.

Full instructions: [docs/INSTALL.md](docs/INSTALL.md).

## Quickstart

### 1. Import or discover leads

```bash
reachy import --file leads/philly_venues_1000.json \
  --source legacy_dataset --list philly_venues

reachy discover "Wedding venues in Philadelphia PA" \
  --limit 25 --list philly_venues --backend playwright
```

### 2. Sample, review, and approve the list

```bash
reachy list sample --list philly_venues --size 10 --seed 42
reachy list review --review-id 1 --incorrect 2,7 --notes "wrong category"
reachy list show --list philly_venues
reachy list approve --list philly_venues --reviewer "Your Name"
```

The sample gate blocks list approval when the configured number of incorrect records is reached (default 2). Review decisions are persisted.

### 3. Connect a sender

Mock sender for a local dry run:

```bash
reachy accounts add-mock
```

SMTP:

```bash
export REACHY_SMTP_PASSWORD='...'
reachy accounts add-smtp \
  --email you@yourdomain.com \
  --host smtp.yourdomain.com --port 587 \
  --imap-host imap.yourdomain.com --imap-port 993 \
  --display-name "Your Name" \
  --password-env REACHY_SMTP_PASSWORD \
  --permitted-use-acknowledged
```

Gmail API (official OAuth, least-privilege scopes):

```bash
# With REACHY_GOOGLE_CLIENT_ID and REACHY_GOOGLE_CLIENT_SECRET in .env (recommended):
reachy accounts add-gmail \
  --email you@yourdomain.com \
  --permitted-use-acknowledged \
  --open-browser

# Or with downloaded client_secrets.json:
reachy accounts add-gmail \
  --email you@yourdomain.com \
  --client-secrets ~/google-oauth-client.json \
  --permitted-use-acknowledged \
  --open-browser
```

See [docs/GMAIL_OAUTH_SETUP.md](docs/GMAIL_OAUTH_SETUP.md) for full Google Cloud Console instructions and scope explanations. Reachy never asks for a Google password.

### 4. Create and run a campaign

`steps.json`:

```json
[
  {
    "subject": "quick question",
    "body": "Hi {{company}} team, I noticed your {{category}} work in {{city}}. Worth a short conversation?",
    "delay_days": 0
  },
  {
    "subject": "following up",
    "body": "Hi {{company}} team, following up on my note about {{category}} in {{city}}.",
    "delay_days": 3
  }
]
```

`policy.json`:

```json
{
  "jurisdiction": "US",
  "lawful_basis": "Documented business-to-business outreach with published business contact details.",
  "policy_reviewed": true,
  "require_personalization_evidence": true
}
```

```bash
reachy campaign create --name "Philly venues Q4" \
  --list philly_venues --account 1 \
  --steps steps.json --policy policy.json \
  --sender-identity "Your Name, Founder" \
  --jurisdiction US --test-send

reachy campaign preview --id 1
reachy campaign approve --id 1 --by "Your Name"
reachy campaign start --id 1
reachy campaign run
```

`--test-send` redirects every message to `REACHY_TEST_RECIPIENT`. Omit `--test-send` only when you intentionally choose a live campaign. `reachy campaign run` processes one batch; schedule it with cron or a service manager if you want continuous delivery.

### 5. Handle replies and health

```bash
reachy replies sync --account 1 --days 14
reachy replies list
reachy replies drafts
reachy replies approve-draft --id 1 --by "Your Name"
reachy health --days 14
```

Reply drafts require human approval and are never auto-sent.

## Commands

```text
reachy init                 Create the database and run migrations
reachy doctor               Diagnose configuration, database, providers, and browser
reachy pause                Enable or disable global pause
reachy import               Import JSON/CSV leads
reachy discover             Browser-assisted Google Maps discovery
reachy leads                Inspect leads
reachy list                 Create lists; sample, review, approve, show
reachy copy                 Styles catalog, sample preview, AI copy generator, spam checker
reachy warmup               Inspect Gmail/SMTP account warmup curve and daily safe limits
reachy accounts             Add/list/check/disconnect senders
reachy campaign             Create/preview/approve/start/plan-batches/run/pause/resume/stop/reconcile/show
reachy agent                Autonomous agent dispatch loop with health checks and safety gates
reachy tracking             Open beacon telemetry and automated bounce monitoring
reachy replies              Sync, list, draft, and approve replies
reachy bounce               Record a hard or soft bounce
reachy suppress             Manage the global suppression list
reachy health               Sender health report
reachy report               Daily outreach, open rate, and deliverability report
reachy export               Export customer data
reachy backup / restore     Back up or restore SQLite
reachy audit                Show the append-only audit log
reachy browser              Playwright diagnostics and interactive profile
```

Most commands accept `--json` before the subcommand.

## Safety and limits

- **Test first.** Use `reachy accounts add-mock`, dry runs, and `REACHY_TEST_RECIPIENT` before any live campaign.
- **Consent is not automatic.** A published business email does not by itself create consent. You are responsible for the lawful basis, jurisdiction rules, and provider terms that apply to your outreach.
- **No bypass.** Reachy does not solve CAPTCHAs, evade rate limits, or circumvent access controls.
- **Browser fragility.** Google Maps markup changes. Selectors may need maintenance, and a blocked or changed page can return no leads rather than incorrect ones.
- **Email verification limits.** `valid` means an explicitly published address on a domain with MX records. It does not prove the mailbox exists.
- **Deliverability claims.** Reachy reports accepted submissions and provider events; it does not guarantee inbox placement.
- **Legacy scripts.** `email_outreach/cold_email_engine.py` remains a non-sending report/simulation tool. Use `reachy` for real delivery.

## Documentation

- [Install](docs/INSTALL.md)
- [Configuration](docs/CONFIGURATION.md)
- [Google OAuth setup](docs/GMAIL_OAUTH_SETUP.md)
- [Security](docs/SECURITY.md)
- [Compliance](docs/COMPLIANCE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Release](docs/RELEASE.md)
- [Dependency licences](docs/DEPENDENCY_LICENSES.md)
- [Audit](docs/AUDIT.md) and [plan](docs/PLAN.md)
- [Agent guide](AGENTS.md)

## MCP

Add to an MCP client:

```json
{
  "mcpServers": {
    "reachy": {
      "command": "python3",
      "args": ["-m", "google_maps_leads.mcp_server"],
      "cwd": "/path/to/Reachy"
    }
  }
}
```

Tools: `extract_google_maps_leads`, `scrape_leads`, `search_and_extract`, `browser_diagnostics`. Email credentials and campaign execution are not exposed over MCP.

## Development

```bash
pip install -e ".[browser,gmail,dev]"
python3 -m pytest -q
```

Tests use mocked providers and test recipients. They do not send real prospect email.

## Licence

MIT. See [LICENSE](LICENSE). Third-party dependency notes are in [docs/DEPENDENCY_LICENSES.md](docs/DEPENDENCY_LICENSES.md).
