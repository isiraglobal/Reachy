# AGENTS.md — Operational guide for Reachy

Reachy is a self-hosted B2B prospecting and outreach application by **ISIRA Automations**. This file tells CLI agents how to install, test, inspect, and operate it without unsafe shortcuts.

## Safety rules

- Never send real prospect email while testing. Use `reachy accounts add-mock`, dry runs, or `REACHY_TEST_RECIPIENT`.
- Never add CAPTCHA solving, access-control evasion, stealth patching, rate-limit circumvention, or account/domain rotation to bypass limits.
- Never fabricate email addresses or mark guessed addresses as verified.
- Never commit secrets, tokens, `.env` files, databases, keys, logs, browser profiles, or customer exports.
- Do not claim inbox placement or "delivered" status without provider evidence.
- A published business email is not automatic consent. Policy gates must remain conservative: unknown or failed checks block.
- Preserve suppression records. Do not delete them to make a campaign pass.

## Architecture

```text
Reachy/
├── reachy/                          # Product runtime and CLI
│   ├── cli.py                       # `reachy` command surface
│   ├── db.py                        # SQLite, migrations, backup/restore, recovery
│   ├── migrations/001_initial.sql   # Versioned schema
│   ├── config.py                    # Paths and environment configuration
│   ├── normalize.py                 # Lead/contact normalization and dedupe
│   ├── verify.py                    # DNS/verification states and SMTP probe
│   ├── scoring.py                   # Evidence-based ICP scoring
│   ├── sample_qc.py                 # Seeded sample, reviews, approval gate
│   ├── suppression.py               # Global suppression
│   ├── policy.py                    # Pre-send compliance gate
│   ├── campaign.py                  # Durable planning, claims, send, reconciliation
│   ├── providers/                   # mock, SMTP/IMAP, Gmail API
│   ├── oauth.py                     # Fernet token storage, Gmail OAuth lifecycle
│   ├── replies.py                   # Reply sync, classification, drafts
│   ├── health.py                    # Sender metrics and auto-pause
│   ├── browser.py                   # Playwright diagnostics and profile
│   ├── ingest.py                    # Import/discovery ingestion
│   ├── web.py                       # Contact extraction from HTML
│   └── logging_utils.py             # JSON logs and secret redaction
├── google_maps_leads/               # Maps scraper, MCP server, legacy CLI
│   ├── scraper.py                   # Playwright-preferred extraction
│   ├── drivers.py                   # Browser driver abstraction
│   ├── browser_test.py              # Playwright diagnostics
│   ├── browser_installer.py         # Installer/diagnostics wrapper
│   ├── mcp_server.py                # MCP stdio tools
│   └── cli.py                       # `reachy-leads`
├── leads/                           # Enrichment and historical datasets
├── email_outreach/                  # Legacy non-sending report/simulation
├── tests/                           # Mocked tests; no real email
├── docs/                            # Install, config, security, compliance, release
├── LICENSE                          # MIT
└── pyproject.toml                   # Dependencies, extras, entrypoints
```

SQLite is the only datastore. The default home is `~/.reachy`; override with `REACHY_HOME` or `--home`.

## Bootstrap

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[browser,gmail,dev]"
python -m playwright install chromium
reachy init
reachy doctor
python3 -m pytest -q
```

On Linux, if Chromium libraries are missing:

```bash
sudo python -m playwright install --with-deps chromium
```

Python 3.10+ is required; the repository is tested on Python 3.13.

## Command surface

```text
reachy init | doctor | pause
reachy icp create|list
reachy import --file FILE --source SOURCE --list NAME
reachy discover "query" --limit N --list NAME [--backend playwright]
reachy leads list [--list NAME] [--limit N]
reachy list create|sample|review|approve|show
reachy copy styles|sample|generate|check-spam
reachy warmup status [--account ID]
reachy accounts add-mock|add-smtp|add-gmail|list|check|disconnect
reachy campaign create|preview|approve|start|plan-batches|run|pause|resume|stop|reconcile|show
reachy agent send [--campaign ID] [--max N] [--pace SECONDS]
reachy tracking record-open|stats
reachy replies sync|list|drafts|approve-draft
reachy bounce | suppress | health | export | backup | restore | audit | report
reachy browser check|open
```

Use `--json` before the subcommand for machine-readable output. Use `python3 -m reachy ...` if the console script is unavailable.

Legacy entrypoints remain: `reachy-leads`, `reachy-mcp`, `reachy-browser-test`, `reachy-browser-install`.

## Safe operating sequence

1. `reachy init` and `reachy doctor`.
2. Import or discover into a named list.
3. `reachy list sample --list NAME --size 10 --seed 42`.
4. Review with `reachy list review --review-id ID --incorrect ...`.
5. Approve only if the sample meets the threshold: `reachy list approve`.
6. Add a mock sender or a real sender with `--permitted-use-acknowledged`.
7. Create a campaign with a policy containing `jurisdiction`, `lawful_basis`, and `policy_reviewed: true`, plus a real `--sender-identity`.
8. Preview, approve, and start.
9. Run with `--test-send` and `REACHY_TEST_RECIPIENT` before any live send.
10. Inspect `reachy campaign show`, `reachy health`, and `reachy audit`.
11. Sync replies and handle suppression/drafts.

Never skip the mock/test stage.

## Testing

- Tests live in `tests/`; run `python3 -m pytest -q`.
- Tests use mocked providers and test recipients. They must never contact real prospects.
- When changing database schema, add a new migration; never edit an applied migration.
- After changes, run `python3 -m compileall -q reachy google_maps_leads leads email_outreach` and the test suite.
- Check `reachy --version`, `reachy --help`, and any changed subcommand help.

## Configuration

Environment variables: `REACHY_HOME`, `REACHY_DB`, `REACHY_SECRET_KEY`, `REACHY_SECRET_KEY_PATH`, `REACHY_LOG`, `REACHY_TEST_RECIPIENT`, `REACHY_ALLOW_CATCH_ALL`, `REACHY_CATCH_ALL_PROBE`, `REACHY_RECONCILE_GRACE`, `REACHY_UNSUBSCRIBE_FOOTER`.

Full details: `docs/CONFIGURATION.md`.

## Provider notes

- **Mock**: records accepted sends locally; does not transmit. Use for workflow tests.
- **SMTP/IMAP**: STARTTLS with certificate verification; IMAP for replies. Password is encrypted.
- **Gmail API**: official OAuth installed-app flow; scopes `gmail.send` and `gmail.readonly`; tokens encrypted; disconnect revokes.
- No provider path automates the Gmail web UI.

## Browser notes

- Playwright is the supported backend; `agent-browser` is a fallback only.
- Persistent profile: `~/.reachy/browser-profile`.
- Never disable TLS verification or run untrusted browser binaries.
- Reachy does not bypass CAPTCHAs or access controls. If a site blocks automation, stop.

## Legacy code

`email_outreach/cold_email_engine.py` is a non-sending report/simulation tool and is not the production sender. `email_outreach/inboxes.json` is intentionally empty; `inboxes.example.json` is documentation only. Use `reachy` for real delivery.

## Documentation map

- `docs/INSTALL.md`
- `docs/CONFIGURATION.md`
- `docs/SECURITY.md`
- `docs/COMPLIANCE.md`
- `docs/TROUBLESHOOTING.md`
- `docs/RELEASE.md`
- `docs/DEPENDENCY_LICENSES.md`
- `docs/AUDIT.md` (historical audit)
- `docs/PLAN.md` (implementation phases)

## Definition of done

A change is done when:

- The behaviour is implemented and documented.
- Tests pass and cover the change, including failure and safety paths.
- No secret, real prospect data, or live send was introduced.
- Policy/suppression guarantees are preserved.
- `compileall` and `pytest` pass.
- The README/AGENTS/docs remain accurate.
