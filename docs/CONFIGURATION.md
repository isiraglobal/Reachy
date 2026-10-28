# Configuration

Reachy reads a small set of environment variables and stores operational data in SQLite. Secrets are stored encrypted in the database, not in configuration files.

## Environment variables

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `REACHY_HOME` | `~/.reachy` | Home for database, key, log, browser profile. |
| `REACHY_DB` | `$REACHY_HOME/reachy.sqlite3` | SQLite database path. |
| `REACHY_SECRET_KEY_PATH` | `$REACHY_HOME/secret.key` | Fernet key file when `REACHY_SECRET_KEY` is not set. |
| `REACHY_SECRET_KEY` | unset | Urlsafe-base64 Fernet key supplied by a secret manager. Takes precedence over the key file. |
| `REACHY_LOG` | `$REACHY_HOME/reachy.log` | Structured application log. |
| `REACHY_TEST_RECIPIENT` | unset | Required for test mode; every test message is redirected here. |
| `REACHY_ALLOW_CATCH_ALL` | `false` | Allow `catch_all` contacts to pass the policy gate. |
| `REACHY_CATCH_ALL_PROBE` | `false` | Enable SMTP catch-all probing during verification. |
| `REACHY_RECONCILE_GRACE` | `900` | Seconds to wait before treating an unresolved uncertain send as failed. |
| `REACHY_UNSUBSCRIBE_FOOTER` | built-in sentence | Footer appended to every outbound body. |

Boolean variables accept `1`, `true`, `yes`, or `on` (case-insensitive).

The CLI also accepts `--home PATH` and `--json` before the subcommand:

```bash
reachy --home /srv/reachy --json health
```

## Filesystem layout

```text
$REACHY_HOME/
├── reachy.sqlite3       # application database
├── secret.key           # created with mode 0600 if REACHY_SECRET_KEY is absent
├── reachy.log           # structured log with secret redaction
└── browser-profile/     # persistent Playwright profile for interactive sign-in
```

`reachy init` creates the home directory with mode `0700`. Back up the database and key separately; the key is required to decrypt stored account secrets. A database backup without the key is not sufficient to restore sending accounts.

## Accounts

Accounts store provider configuration plus encrypted credentials. `reachy accounts list` deliberately omits `config_json`.

### SMTP

Required: `--email`, `--host`. Optional: `--port` (default 587), `--username` (default email), `--imap-host`, `--imap-port` (default 993), `--display-name`, `--password-env`, `--daily-limit` (default 10), `--permitted-use-acknowledged`.

TLS is required. Reachy uses STARTTLS where advertised (and on port 587) and verifies certificates. IMAP is used only when `--imap-host` is configured.

### Gmail API

Required: `--email`, `--client-secrets`. Optional: `--display-name`, `--daily-limit`, `--port` for the local OAuth callback, `--open-browser`, `--permitted-use-acknowledged`.

Scopes are limited to `gmail.send` and `gmail.readonly` plus OpenID/email identity. Tokens are encrypted. `reachy accounts disconnect --id N` revokes the token with Google and deletes the local secret.

### Mock

`reachy accounts add-mock` creates an active local sender. Mock sends are recorded as accepted but are not transmitted.

## Campaign policy

A campaign policy is a JSON object. The approval gate requires:

| Field | Requirement |
| :--- | :--- |
| `jurisdiction` | Non-empty country code, normally `US`. Must be in the policy allow-list. |
| `lawful_basis` | Non-empty description of why the outreach is permitted. |
| `policy_reviewed` | `true` only after a human reviewed the campaign. |
| `sender_identity` | Set on the campaign (`--sender-identity`) with the real sender name and role. |
| `require_personalization_evidence` | Default `true`; templates must reference at least one real lead/contact field. |
| `allow_catch_all` | Optional; overrides `REACHY_ALLOW_CATCH_ALL` for this campaign. |

The default policy allow-list is `US`. It is enforced in code; changing the allow-list is a code change and should be a reviewed compliance decision.

Live sends additionally require an `ACTIVE` sender with `authorized_at`, permitted-use acknowledgement, remaining daily quota, an approved list, a verified contact with an explicit source, and no suppression match. Missing or unknown values block the send.

## Templates

Available variables:

```text
{{company}} {{city}} {{state}} {{category}}
{{reviews_count}} {{rating}} {{website}} {{phone}} {{email}}
```

Missing values raise an error and the message is blocked; Reachy does not insert placeholders or invent facts. At least one evidence variable is required by default.

## Campaign modes

| Mode | Flags | Behaviour |
| :--- | :--- | :--- |
| Dry run | default (`campaign create` without send flags) | Plans the full sequence; records `SKIPPED` without submitting. |
| Test send | `--test-send` | Submits only to `REACHY_TEST_RECIPIENT`. Requires approval and an active sender. |
| Live send | `--live-send` | Submits to prospect addresses after approval. Use deliberately. |

`reachy campaign start` plans every step for every primary contact before any submission. Follow-ups are cancelled on reply, unsubscribe, complaint, hard bounce, stop, or global pause.

## Reply sync

```bash
reachy replies sync --account 1 --days 14
```

SMTP accounts need `--imap-host`. Gmail accounts use the API. Replies are deduplicated by provider message ID and by `Message-ID`. Classification is rule-based; unsubscribe and complaint take precedence. Complaints and unsubscribes are added to the global suppression list.

Reply drafts are generated locally and require:

```bash
reachy replies approve-draft --id N --by "Your Name"
```

Approval records the decision. Reachy does not auto-send drafts.

## Health and global pause

```bash
reachy health --days 14
reachy health --account 1 --check-provider
reachy pause
reachy pause --resume
```

Health metrics include accepted submissions, hard bounces, complaints, unsubscribe replies, positive replies, and sync lag. "Delivered" and "inbox placement" remain unknown unless the provider supplies a real event.

Health alerts auto-pause an account when thresholds are exceeded. Disable with `--no-auto-pause` for a one-off report.

## Suppression management

```bash
reachy suppress add --email person@example.com --reason unsubscribe
reachy suppress list
reachy suppress remove --email person@example.com --force
```

`unsubscribe`, `complaint`, and `legal` records require `--force` after review. Removing a suppression only removes the record; it does not restore consent or erase the audit trail. Preserve records unless they were entered in error.

## Export and backup

```bash
reachy export --out ./reachy-export
reachy backup --out ./reachy-$(date +%F).sqlite3
reachy restore --from ./reachy-2026-10-23.sqlite3
```

`export` writes one JSON file with the customer tables; it omits account configuration and scopes and never includes the encryption key. `backup` uses SQLite's online backup API. `restore` requires the worker to be stopped and the current database moved aside first; it copies the backup into place without creating an automatic safety copy.
