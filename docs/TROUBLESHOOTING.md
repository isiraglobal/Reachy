# Troubleshooting

Start with:

```bash
reachy doctor
reachy browser check --json
reachy health --days 14
reachy campaign show --id N
reachy audit --limit 50
```

Use `--json` before the subcommand for machine-readable output.

## Installation

### `reachy: command not found`

The virtual environment is not active, or the package is not installed in it.

```bash
source .venv/bin/activate
pip install -e ".[browser,gmail]"
which reachy
```

### `No module named playwright` / `No module named google...`

Install the relevant extra:

```bash
pip install -e ".[browser]"
pip install -e ".[gmail]"
```

Then reinstall the local package if you changed extras.

### `reachy --version` works from the repo but not elsewhere

Use the virtual environment's absolute path in cron/systemd, for example `/opt/Reachy/.venv/bin/reachy`.

## Browser and discovery

### `Playwright is not installed` or browser check fails

```bash
python -m playwright install chromium
reachy browser check
```

On Linux, missing shared libraries show up as `libnss3`, `libatk`, `libgbm`, `libasound`, `libxkbcommon`, or `error while loading shared libraries`:

```bash
sudo python -m playwright install --with-deps chromium
```

If `--with-deps` is unavailable, install the packages named in the error for your distribution. Do not disable TLS or run downloaded binaries from untrusted sources.

### Discovery returns zero leads

- Google Maps DOM/selectors may have changed.
- The page may be blocked, showing a consent screen, or requiring sign-in.
- Run `reachy doctor --headed` or `reachy browser check --headed` to inspect.
- Try a less specific query or a smaller limit.
- Reachy does not bypass CAPTCHAs or access controls. If Maps blocks the session, stop and use an allowed data source.

### `agent-browser` fallback fails

Playwright is the supported backend. Install it and use `--backend playwright` or `--backend auto`. The fallback is retained only for environments that already depend on `agent-browser`.

### Contacts are missing or `unverified`

Enrichment depends on public pages. Sites may hide email behind forms, JavaScript challenges, or images. Reachy does not guess addresses. Check the lead's website, source URL, and verification status:

```bash
reachy leads list --list YOUR_LIST --limit 20
```

## Lists and sample review

### `list is not approved` / `Lead list is not approved through sample review`

Create a sample, review it, and approve the list:

```bash
reachy list sample --list YOUR_LIST --size 10 --seed 42
reachy list review --review-id N --incorrect 1,5
reachy list approve --list YOUR_LIST --reviewer "Your Name"
```

If the incorrect count reaches the threshold (default 2), approval is blocked. Improve the list or create a new sample after fixing data. Decisions are persisted.

### `Contact verification state is 'unknown'`

The address may be on a domain with no MX record, a temporary DNS failure, or a source that is not explicitly published. Re-import/verify later, or exclude the contact. Unknown never passes live policy.

## Accounts and authentication

### `invalid REACHY_SECRET_KEY / key file`

The key is not valid urlsafe-base64 Fernet material. Either fix the environment variable or remove/restore the correct `secret.key`. Do not generate a new key unless you intend to re-authorize every account.

### `SMTP authentication failed`

- Confirm host, port, username, and password/app-password.
- Many providers require an app password or SMTP-specific credential.
- Confirm the provider allows SMTP and that TLS/STARTTLS is available.
- Check `reachy accounts check`.

Passwords are read from the environment variable named by `--password-env` or prompted at add time. Reachy never prints them.

### Gmail OAuth fails or `invalid_grant`

- Confirm the OAuth client is type **Desktop app**.
- Confirm the Gmail API is enabled in the same Google Cloud project.
- Confirm the consent screen is configured and your account is allowed while the app is in testing.
- Re-authorize with `reachy accounts add-gmail ...` or disconnect and reconnect.
- If a token was revoked or expired beyond refresh, disconnect the account and authorize again:

```bash
reachy accounts disconnect --id N
```

### `Provider permitted-use acknowledgement is missing`

Re-add the sender with `--permitted-use-acknowledged` after you have reviewed the provider's terms. This is required for live sends.

## Campaigns and sending

### Message is `BLOCKED`

Inspect the stored reasons:

```bash
reachy campaign show --id N
reachy audit --limit 50
```

Common reasons:

| Reason | Fix |
| :--- | :--- |
| Global pause is active | `reachy pause --resume` |
| Campaign is not running | `reachy campaign start --id N` |
| Campaign has no recorded approval | `reachy campaign approve --id N --by "Name"` |
| Lead list is not approved | Run sample/review/approve |
| Contact verification state is ... | Use a verified published address or exclude |
| Contact is on the global suppression list | Do not contact; remove only if recorded in error. Unsubscribe/complaint/legal records require reviewed `--force`. |
| Jurisdiction ... not in the configured allow-list | Use a supported jurisdiction; changing the allow-list is a reviewed code change |
| Daily sending limit reached | Wait for the next day or adjust limits deliberately |
| Sender identity is not declared | Re-create/update the campaign with `--sender-identity` |
| Test mode requires REACHY_TEST_RECIPIENT | Set the variable and restart the command |
| Template variable ... has no real evidence | Remove the variable or fix the lead data |

### `a live campaign requires an active authorized sending account`

Check `reachy accounts list`; the account must be `ACTIVE`, have `authorized_at`, and not be revoked. Re-authorize Gmail or re-add SMTP if needed.

### Test sends go to the wrong place

That is intentional. In test mode every message is redirected to `REACHY_TEST_RECIPIENT`. Check the audit/events and do not remove test mode until you are ready for a live campaign.

### Nothing sends even though the campaign is running

`reachy campaign run` processes a finite batch. Run it again or schedule it. Check:

```bash
reachy campaign show --id N
reachy health --days 14
```

Pending messages may be scheduled in the future (follow-up delays) or blocked by quota/policy.

### Uncertain sends

If SMTP loses the connection after submission, the message becomes `UNCERTAIN` rather than being retried. Wait for the grace period, then:

```bash
reachy campaign reconcile --id N
```

Reconciliation looks up the Message-ID at the provider. If it cannot be found after the grace period, the message is failed, not blindly re-sent.

### Sender auto-paused by health checks

```bash
reachy health --days 14 --account N
```

Review bounce/complaint/failure rates. Fix the list or copy, then resume the account deliberately:

```bash
reachy campaign resume --id N
```

Use `--no-auto-pause` only for reporting, not to keep a failing sender active.

## Replies

### No replies found

- SMTP accounts need `--imap-host` and valid IMAP credentials.
- Gmail needs `gmail.readonly` authorization; re-authorize after changing scopes.
- Reachy syncs unseen messages by default. Check the account's inbox and provider settings.
- Run with a larger `--days` window.

### Duplicate replies

Replies are deduplicated by provider message ID and `Message-ID`. If a provider changes IDs between syncs, duplicates can occur. Do not delete suppression or reply records to "clean up"; investigate first.

### A draft was not sent

By design. Drafts require human approval and are never auto-sent. Approve and send from your normal mail client or extend the workflow deliberately.

## Database and operations

### `database is locked`

SQLite is waiting on another process. Ensure cron/systemd is not launching overlapping long workers. `PRAGMA busy_timeout` is 30 seconds. Stop extra workers, then retry. Do not delete the WAL file while a process is running.

### Restore refuses to run

`reachy restore` deliberately requires the live database to be absent:

```bash
reachy pause
# stop the worker
mv ~/.reachy/reachy.sqlite3 ~/.reachy/reachy.sqlite3.before-restore
reachy restore --from /path/to/backup.sqlite3
reachy doctor
```

Restore does not create an automatic safety copy. Keep the moved-aside file and the matching encryption key.

### Exported data is missing accounts/secrets

`reachy export` intentionally omits account configuration and scopes, and never exports the encryption key or decrypted credentials. Use a protected database backup when you need a full restore.

## Getting help

Collect `reachy doctor --json`, the failing command, and relevant audit rows. Redact email addresses, tokens, passwords, and customer data before sharing logs.
