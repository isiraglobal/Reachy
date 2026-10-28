# Security

Reachy handles business contact data and email credentials. Treat the machine that runs it as a trusted administrative host.

## Supported versions

| Version | Supported |
| :--- | :--- |
| 2.0.x | Yes |
| < 2.0 | No |

Report vulnerabilities privately to the maintainers listed in `pyproject.toml` (ISIRA Automations, `automations@isira.org`). Do not open a public issue containing credentials, tokens, customer data, or reproduction steps that expose a live account.

## Threat model

Reachy is a local CLI and worker. It has no inbound HTTP service and no multi-tenant user system. Its main assets are:

- Sending-account passwords and OAuth refresh tokens.
- The encryption key that protects those secrets.
- Business contact data and message history.
- The ability to send email as the configured sender.

Primary risks:

1. Local compromise of the host or the user account running Reachy.
2. Leakage of the database, key file, backups, logs, or exported data.
3. Accidental live sends during testing or misconfiguration.
4. Provider compromise or OAuth token theft.
5. Malicious or unexpected content from browsed pages and inbound email.

Out of scope: defending against a hostile root user on the same host, or providing a hardened sandbox for arbitrary untrusted code.

## Secret handling

- SMTP passwords and OAuth token payloads are encrypted with Fernet before being written to `account_secrets`.
- The key is read from `REACHY_SECRET_KEY` or a key file created with mode `0600`.
- The CLI never prints stored passwords or tokens. `accounts list` omits `config_json`.
- Logs run through a redaction filter for password, secret, token, authorization, cookie, API-key, and private-key patterns. Message bodies are not logged by default.
- OAuth scopes are limited to `gmail.send`, `gmail.readonly`, and identity.
- `accounts disconnect` revokes the Google token and deletes the local secret.

Limits: redaction is best-effort pattern matching, not a formal data-loss-prevention system. Do not log or paste secrets intentionally. A database backup is sensitive even though secrets are encrypted; protect it like a credential store.

Key rotation is not automated. To rotate, re-authorize each account under the new key or decrypt and re-encrypt the stored payloads with a reviewed procedure.

## Transport security

- SMTP uses STARTTLS where available and on port 587, with certificate verification through the system trust store.
- IMAP uses `IMAP4_SSL` with certificate verification.
- Gmail uses the official HTTPS API.
- Contact-page fetching verifies TLS certificates. The historical `CERT_NONE` path was removed.
- Browser traffic uses Playwright's Chromium and its normal certificate handling.

## Browser isolation

- Browser automation is separated from email credentials and campaign execution.
- Agent-facing URL extraction only accepts HTTP/HTTPS and rejects literal private, loopback, link-local, and metadata addresses. This is a best-effort SSRF guard, not a replacement for network egress controls.
- Playwright is the supported backend. The legacy `agent-browser` path is a fallback only.
- Reachy does not solve CAPTCHAs, bypass access controls, evade rate limits, or use stealth patches.
- The persistent browser profile may contain cookies for sites you sign into manually. It is stored under `~/.reachy/browser-profile` with directory mode `0700`.
- Do not sign into sensitive accounts in the automation profile unless necessary. Use a dedicated profile.

## Sending safety

- Live campaigns require list approval, campaign approval, an active authorized sender, permitted-use acknowledgement, a compliant policy record, a verified explicitly sourced contact, and no suppression match.
- Test mode redirects every recipient to `REACHY_TEST_RECIPIENT`.
- Dry run plans messages without submitting.
- Global pause and per-account daily limits are enforced before submission.
- An uncertain SMTP/API result is not retried blindly; it is reconciled by Message-ID after a grace period.
- Follow-ups are cancelled on reply, unsubscribe, complaint, hard bounce, stop, or pause.

## Data protection

- Reachy creates the home directory with mode `0700` and the database, backups, keys, and exports with mode `0600` where the platform permits.
- Store `~/.reachy` and backups on encrypted disks where possible.
- Restrict filesystem access to the service account.
- Export only the data you need and delete exports when finished.
- Define a retention period for leads, messages, replies, and logs. Reachy does not delete data automatically.
- Suppression records must be retained even after other data is deleted, so future imports do not re-contact opted-out people.
- On decommissioning, revoke OAuth tokens and destroy the database and key.

## Operator checklist

- [ ] `REACHY_SECRET_KEY` is supplied from a secret manager or the key file is `0600`.
- [ ] The database, backups, exports, and logs are not in a web root or shared folder.
- [ ] `reachy doctor` passes; `reachy browser check` passes.
- [ ] A mock or test-recipient campaign passes end to end before live sending.
- [ ] Global pause is known and tested.
- [ ] Sender accounts use dedicated domains/identities you are authorized to use.
- [ ] Daily limits reflect provider terms and your reputation strategy.
- [ ] OAuth client secrets and tokens are not committed to the repository.
- [ ] Backups are encrypted and the key is backed up separately.
- [ ] A human reviews sample lists and campaign copy.
- [ ] Suppression and unsubscribe handling are tested.
- [ ] Incident contact and token-revocation steps are documented for your team.
