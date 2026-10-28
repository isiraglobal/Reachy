# Install Reachy

Reachy runs locally or on a customer-controlled VPS. Python 3.10+ is required; this repository is tested on Python 3.13.

## 1. System requirements

- macOS or Linux. Windows is not tested.
- Python 3.10 or newer with `pip` and `venv`.
- SQLite is bundled with Python; no separate database server is required.
- For browser discovery: Playwright plus Chromium.
- For Gmail sending: a Google Cloud OAuth client of type **Desktop app**.

Disk usage is small. The database and browser profile live under `~/.reachy` by default.

## 2. Install from source

```bash
git clone https://github.com/isiraglobal/Reachy.git
cd Reachy
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[browser,gmail]"
```

Extras:

| Extra | Adds | Needed for |
| :--- | :--- | :--- |
| `browser` | Playwright | Maps discovery, browser diagnostics |
| `gmail` | Google auth/API libraries | Gmail API sending and reply sync |
| `dev` | pytest, pytest-cov | Tests |

SMTP/IMAP sending works without the `gmail` extra. Browser commands fail with a remediation message if `browser` is missing.

## 3. Install Chromium

```bash
python -m playwright install chromium
```

On Linux, install the required system libraries:

```bash
sudo python -m playwright install --with-deps chromium
```

If `--with-deps` is unavailable, install the distribution packages reported by:

```bash
reachy browser check --json
```

Do not install Chromium system-wide as a workaround unless your distribution requires it; the Playwright-managed browser is the supported binary.

## 4. Initialize and diagnose

```bash
reachy init
reachy doctor
reachy browser check
```

`reachy init` creates the SQLite database and runs migrations. It is idempotent.

`reachy doctor` checks the home directory, database, configuration, accounts, and browser. Use `reachy doctor --json` for machine-readable output.

## 5. Configure storage and secrets

Defaults:

```text
~/.reachy/reachy.sqlite3
~/.reachy/secret.key
~/.reachy/reachy.log
~/.reachy/browser-profile/
```

Override the home directory with `REACHY_HOME` or `--home`. Do not place the database or key file in a public web root or a shared directory.

For production, provide the Fernet key through a secret manager rather than a file:

```bash
export REACHY_SECRET_KEY='<urlsafe-base64-32-byte-key>'
```

Generate a key once with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Changing the key without re-encrypting stored secrets makes existing account credentials unreadable. Back up the key separately from the database.

## 6. Connect a sender

Mock sender, for local workflow testing:

```bash
reachy accounts add-mock --email test@example.invalid
```

Mock sends are recorded in the database but are not delivered.

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
reachy accounts check
```

If `--password-env` is omitted, Reachy prompts for the password. Passwords are encrypted before storage.

Gmail API:

1. In Google Cloud Console, enable the Gmail API.
2. Configure the OAuth consent screen for your organization.
3. Create an OAuth client of type **Desktop app** and download the JSON file.
4. Authorize:

```bash
reachy accounts add-gmail \
  --email you@yourdomain.com \
  --client-secrets ~/google-oauth-client.json \
  --display-name "Your Name" \
  --permitted-use-acknowledged \
  --open-browser
```

Reachy requests `gmail.send` and `gmail.readonly` only. It does not request your Google password and does not automate the Gmail web UI.

## 7. First run

```bash
reachy import --file leads/philly_venues_1000.json \
  --source legacy_dataset --list demo
reachy list sample --list demo --size 10 --seed 42
reachy list show --list demo
```

Review the sample, then approve the list only if it meets your standard. A live campaign also needs:

- `REACHY_TEST_RECIPIENT` for test mode.
- A campaign policy with jurisdiction, lawful basis, and `policy_reviewed: true`.
- An active, authorized sender with permitted-use acknowledgement.

## 8. Run as a service

Reachy is a CLI, not a daemon. To run campaigns continuously, invoke `reachy campaign run` from cron or systemd and keep `reachy pause` available as an operator kill switch.

Example cron entry (every five minutes):

```cron
*/5 * * * * cd /opt/Reachy && /opt/Reachy/.venv/bin/reachy campaign run --max 20 >> /var/log/reachy-worker.log 2>&1
```

Use one worker per database by default. Multiple workers are protected by atomic claims, but a single worker is easier to operate.

## 9. Upgrade

```bash
cd /opt/Reachy
source .venv/bin/activate
git pull
pip install -e ".[browser,gmail]"
python -m playwright install chromium
reachy init
reachy doctor
```

Back up before upgrading:

```bash
reachy backup --out ~/reachy-backup-$(date +%F).sqlite3
```

## 10. Uninstall

```bash
pip uninstall reachy
```

Removing the package does not delete `~/.reachy`. Delete that directory only after exporting data and confirming you no longer need the database or encryption key.
