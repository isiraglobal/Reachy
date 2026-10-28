# Legacy outreach report engine

Part of **Reachy** by **ISIRA Automations**.

This directory contains a **non-sending** reporting/simulation script retained for historical context. It does not deliver email, does not connect to a sending provider, and is not the production sender.

Use `reachy` for real delivery, suppression, policy gates, OAuth, campaign execution, replies, and health.

## What this script does

`cold_email_engine.py` reads lead data and `inboxes.json`, applies volume/quality heuristics, generates copy samples, and writes a local JSON report. It records simulated `QUEUED_FOR_DISPATCH` states only.

It does not:

- Open an SMTP connection or call a provider API.
- Store or validate sender credentials.
- Enforce suppression, consent, jurisdiction, or unsubscribe rules.
- Verify mailbox existence or inbox placement.
- Guarantee deliverability, reply rates, or phone/email match rates.

Do not treat its report as evidence of delivery or campaign success.

## Files

| File | Description |
| :--- | :--- |
| `cold_email_engine.py` | Legacy report/simulation generator. No sending code. |
| `inboxes.json` | Intentionally empty. Do not add real credentials; this legacy script does not encrypt or authorize them. |
| `inboxes.example.json` | Illustrative schema only, with non-deliverable placeholders. |

## Running it

```bash
python3 email_outreach/cold_email_engine.py
```

The script writes a generated report to `final_outreach_execution_report.json` (ignored by git) and prints summaries. Review the output as a simulation, not as proof of any real-world outcome.

## Production path

```bash
reachy init
reachy accounts add-mock       # or add-smtp / add-gmail
reachy list sample --list NAME
reachy list approve --list NAME
reachy campaign create --name NAME --list NAME --steps steps.json --policy policy.json
```

See the repository [README](../README.md) and [docs/COMPLIANCE.md](../docs/COMPLIANCE.md).
