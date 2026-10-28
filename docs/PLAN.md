# Reachy Consolidation Plan

Execution is phased so every phase is independently testable. `pytest` is run after each phase.

## Phase 0 — Baseline (complete)

- Audit repository, history, dependencies, data.
- Record defects in `docs/AUDIT.md`.

## Phase 1 — Core runtime and storage (complete)

- Add `reachy/` package: config, structured logging with redaction.
- SQLite database with versioned migrations, WAL, foreign keys, backup/restore.
- Tables: leads, contacts, lists, sample reviews/approvals, suppression, accounts, secrets,
  campaigns, steps, messages, events, replies, reply drafts, audit log, health snapshots.
- Tests: migrations idempotency, backup/restore, concurrency claim, redaction.

## Phase 2 — Lead quality (complete)

- Normalize leads/contacts; preserve `raw_json`, source URL, discovery timestamp.
- Deduplicate businesses across sessions and contacts within a business.
- Verification states: `valid`, `invalid`, `catch_all`, `unknown`, `unverified`.
  No guessing, no fabricated addresses.
- ICP profiles with transparent, evidence-based scoring and conflict flags.
- Import existing datasets without altering the originals.

## Phase 3 — Quality and compliance gates (complete)

- Reproducible seeded 10-record sample with source/verification/qualification reason.
- Review decisions persisted; threshold (default 2) blocks list activation.
- Global suppression list that survives campaigns/imports/restarts.
- Pre-send policy engine: source, jurisdiction, provider permitted use, suppression,
  verification, campaign/list approval, sender authorization, limits.
  Any unknown/failed check blocks.

## Phase 4 — Providers and accounts (complete)

- Provider interface with Mock, SMTP/IMAP, and Gmail API implementations.
- Fernet-encrypted token/password storage with 0600 key file or `REACHY_SECRET_KEY`.
- Gmail OAuth installed-app flow, refresh, revocation, disconnect.
- Least-privilege scopes (`gmail.send`, `gmail.readonly`).
- No Gmail web-UI automation, no hard-coded secrets.

## Phase 5 — Campaign execution (complete)

- Explicit campaign states; approvals; preview; dry-run and test-recipient modes.
- All intended messages persisted before submission (full sequence).
- Idempotency key per (campaign, contact, step); concurrency-safe claim.
- Uncertain sends reconciled by Message-ID; no blind retry.
- Follow-ups cancel on reply, unsubscribe, bounce, complaint.
- Global pause, per-account quotas, append-only audit events.

## Phase 6 — Replies, health, operations (complete)

- Reply sync, dedupe, association, rule-based classification with
  unsubscribe/complaint precedence, follow-up cancellation.
- Generated reply drafts require human approval; never auto-sent.
- Sender health metrics and configurable auto-pause thresholds.
- Export, backup/restore, doctor/diagnostics, logging, documentation.

## Phase 7 — Browser (complete)

- Playwright diagnostics: binary, version, launch, missing system deps.
- Headed/headless; persistent local profile for interactive authentication.
- Scraper driver abstraction: Playwright preferred, `agent-browser` fallback.
- Browser isolation from email credentials and campaign execution.

## Phase 8 — Commercial readiness (complete)

- Dependency/licence report, security model, install/config/troubleshooting/release docs.
- Tests cover browser failures, dedupe, verification, sample approvals, token expiry/revocation,
  provider failures, duplicate/concurrent jobs, uncertain sends, reply duplication,
  suppression propagation, follow-up cancellation, restart recovery, secret redaction,
  global pause and policy gates.
