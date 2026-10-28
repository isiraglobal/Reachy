# Contributing to Reachy

Thank you for your interest in contributing to **Reachy**, the open-source autonomous prospecting and cold outreach engine built by **ISIRA Automations**.

We welcome contributions that improve reliability, enrich lead discovery, enhance security, and uphold strict deliverability and compliance standards.

---

## Code of Conduct & Safety Principles

Reachy is built on conservative, privacy-first principles:
1. **Zero Evasion**: We do not accept PRs containing CAPTCHA bypasses, access-control evasion, rate-limit circumvention, or domain rotation designed to evade spam filters.
2. **Never Fabricate Data**: Email addresses must never be guessed, fabricated, or marked `valid` without verified MX / public source evidence.
3. **No Secrets in Code**: Never commit API keys, client secrets, `.env` files, databases, or customer exports.
4. **Preserve Suppressions**: Global suppression records and unsubscribe precedence must remain absolute.

---

## Development Setup

1. Fork and clone the repository:
   ```bash
   git clone https://github.com/isiraglobal/Reachy.git
   cd Reachy
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install editable package with development extras:
   ```bash
   pip install -e ".[browser,gmail,dev]"
   python -m playwright install chromium
   ```

4. Initialize local SQLite database and verify setup:
   ```bash
   reachy init
   reachy doctor
   ```

---

## Making Changes

1. Create a dedicated branch:
   ```bash
   git checkout -b feature/my-enhancement
   ```

2. Ensure code compiles without syntax errors:
   ```bash
   python -m compileall -q reachy google_maps_leads leads email_outreach
   ```

3. Check CLI functionality:
   ```bash
   reachy --help
   reachy doctor
   ```

4. Submit a Pull Request targeting `main`. Please use the provided PR template.
