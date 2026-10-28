# Compliance and acceptable use

This document describes how Reachy's controls map to common outreach obligations. It is not legal advice. Laws, provider terms, and regulator guidance vary by jurisdiction and change over time. Obtain advice for your use case.

## Your responsibilities

You are the sender and the data controller/operator for your campaigns. Before using Reachy you must establish:

- Which jurisdictions you are contacting and which rules apply.
- A lawful basis or permission for each campaign, and whether B2B rules differ from consumer rules.
- Whether your source data and discovery method are permitted by the source's terms.
- Accurate sender identity, physical address, and a functioning opt-out mechanism.
- Retention, access, deletion, and incident-response obligations.
- That your sending provider permits your outreach.

Reachy provides technical gates; it does not make a campaign lawful.

## What Reachy does

| Control | Behaviour |
| :--- | :--- |
| Published-source verification | A contact is `valid` only when it was explicitly published by the business and its domain has MX records. Addresses are never guessed. |
| Explicit discovery methods | Only methods such as website crawl, structured data, Cloudflare-protected email, manual entry, CSV import, and API are accepted for sending. |
| Source retention | Contacts keep their source and source URL. |
| Global suppression | Unsubscribe, complaint, hard bounce, legal, and manual suppressions survive campaigns and imports. |
| Reply precedence | Complaint and unsubscribe classifiers run before every other classification. |
| Follow-up cancellation | Replies, unsubscribes, complaints, and hard bounces cancel pending follow-ups. |
| Campaign policy record | Live sends require jurisdiction, lawful basis, human policy review, and a recorded sender identity. |
| Jurisdiction gate | The default allow-list is `US`; unsupported jurisdictions block. |
| Provider acknowledgement | Each sender must record that the provider's permitted-use terms were acknowledged. |
| Test and dry run | Test mode redirects to one test recipient; dry run does not submit. |
| Daily limits | Per-account limits cap submissions. |
| Audit trail | Account, list, campaign, message, reply, and suppression actions are recorded. |
| No bypass | No CAPTCHA solving, access-control evasion, stealth patching, or rate-limit circumvention. |
| No placement claims | Reachy does not claim inbox placement or delivery without provider evidence. |

## What Reachy does not do

- It does not determine whether your lawful basis is valid.
- It does not obtain consent.
- It does not scrape private, gated, or logged-in data.
- It does not verify that a mailbox exists unless an SMTP probe is explicitly enabled.
- It does not guarantee that a provider will accept or deliver a message.
- It does not automatically honor a jurisdiction's full legal requirements (for example, statutory wording, footer content, or local registration).
- It does not replace a suppression/do-not-contact process outside Reachy. Import and reconcile external suppression lists.

## Common frameworks

### United States (CAN-SPAM)

Commercial email generally requires accurate header information, a non-deceptive subject line, identification of the message as an advertisement where applicable, a valid physical postal address, and a clear opt-out mechanism that is honored promptly. Reachy supports suppression and cancellation but does not insert a postal address automatically. Add your address to campaign copy or a compliant footer and review the result.

### EU/UK (GDPR and ePrivacy/PECR)

B2B outreach can still involve personal data and electronic-marketing rules. You need a documented lawful basis, transparency information, and a valid route to object or opt out. Member-state implementation of B2B rules differs. Reachy's jurisdiction gate defaults to `US`; do not assume that adding `EU` or `UK` to a code allow-list makes a campaign compliant. Review the specific country rules first.

### Other jurisdictions

Canada's CASL, Australia's Spam Act, and similar regimes may require consent, identification, and functional unsubscribe handling. Configure your copy, data sources, and suppression process accordingly.

## Google Maps and Google API terms

Browser-assisted Maps extraction is subject to Google's terms and applicable law. Reachy does not bypass Google's technical restrictions, but you are responsible for whether your use of Maps data is permitted. Do not use Reachy to build a competing mapping service or to harvest data at a scale or in a manner prohibited by the applicable terms.

Gmail sending and reading are subject to Google API Services User Data Policy, OAuth verification requirements, quotas, and your Google Cloud project configuration. Use least-privilege scopes (`gmail.send`, `gmail.readonly`), a dedicated OAuth client, and a consent screen that accurately describes your use.

## Email provider terms

SMTP and API providers impose acceptable-use, sending, and reputation rules. A provider acknowledgement checkbox in Reachy is a record of your decision, not a substitute for reading the provider's terms. Provider suspensions are your responsibility to resolve.

## Data minimization and retention

Collect only contact details needed for the campaign. Keep source/provenance. Avoid enrichment that infers sensitive attributes. Define retention for leads, messages, replies, and logs. Retain suppression records so opted-out people are not re-contacted. Honor deletion and objection requests across imports and backups.

## Prohibited uses

Do not use Reachy to:

- Send to purchased or scraped lists where the source terms or law prohibit it.
- Impersonate a person or organization.
- Hide the sender's identity or forge headers.
- Bypass CAPTCHAs, authentication, paywalls, rate limits, or access controls.
- Send unlawful, harassing, fraudulent, or malicious content.
- Evade provider limits through account or domain rotation.
- Contact people who have opted out, complained, or are legally suppressed.
- Process special-category data without an appropriate legal basis and safeguards.

## Incident response

If you suspect unauthorized sending, credential compromise, or a data breach:

1. Run `reachy pause` to stop submissions.
2. Revoke affected OAuth tokens (`reachy accounts disconnect --id N`) and rotate SMTP passwords.
3. Preserve logs, audit records, and the database for investigation.
4. Notify your provider and affected parties as required.
5. Correct the root cause before resuming; test with a mock account or test recipient.

## Record keeping

Keep campaign policy records, approval decisions, sample reviews, suppression records, and audit logs for the period required by your obligations. Reachy's audit log is append-only at the application level but can be altered by anyone with database access; protect the host and backups accordingly.
