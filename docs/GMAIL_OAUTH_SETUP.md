# Google OAuth 2.0 Setup Guide for Reachy

Reachy connects to Gmail using Google's official, least-privilege OAuth 2.0 installed-application authorization flow.

Tokens are stored encrypted with Fernet symmetric encryption in the local SQLite database. No Gmail passwords are ever requested or stored.

---

## 1. Quick Start via `.env`

Instead of downloading JSON files and passing file paths, you can simply add your Google Client ID and Secret to `.env` (or `~/.reachy/.env`):

```bash
cp .env.example .env
```

Set:
```bash
REACHY_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
REACHY_GOOGLE_CLIENT_SECRET=GOCSPX-your-client-secret
```

Then authorize your sending account:
```bash
reachy accounts add-gmail --email you@example.com --permitted-use-acknowledged --open-browser
```

Reachy automatically launches the Google OAuth consent flow, retrieves the cryptographic tokens, encrypts them, and marks the account `ACTIVE`.

---

## 2. Google Cloud Console Step-by-Step

Follow these steps in the [Google Cloud Console](https://console.cloud.google.com) to obtain your OAuth 2.0 Client credentials:

### Step 1: Create a Project
1. Log into [Google Cloud Console](https://console.cloud.google.com).
2. Click the project dropdown in the top navigation bar and select **New Project**.
3. Name your project (e.g., `reachy-outreach`) and click **Create**.

### Step 2: Enable the Gmail API
1. In the search bar, search for **Gmail API**.
2. Click **Enable**.

### Step 3: Configure the OAuth Consent Screen
1. In the left navigation, go to **APIs & Services** > **OAuth consent screen**.
2. Select **User Type**:
   - **Internal**: If using Google Workspace and sending only within your organization or authorized workspace.
   - **External**: For standard Gmail or cross-organization outreach.
3. Click **Create**.
4. Fill in the App Information:
   - **App name**: `Reachy (ISIRA Automations)`
   - **User support email**: Your email address
   - **Developer contact information**: Your email address
5. Click **Save and Continue**.

### Step 4: Scopes Selection & Rationale
Click **Add or Remove Scopes**. Select only the following four scopes:

| Scope | Type | Purpose & Security Rationale |
| :--- | :--- | :--- |
| `https://www.googleapis.com/auth/gmail.send` | Sensitive | **Outbound Transmission Only**: Permits sending outreach messages. Does not allow reading past inbox mail, modifying drafts, or deleting messages. |
| `https://www.googleapis.com/auth/gmail.readonly` | Sensitive | **Reply & Bounce Tracking**: Permits reading incoming reply headers (`Message-ID`, `In-Reply-To`) to detect replies, classify intent, and catch automated delivery failure notices (DSNs / 550 bounces). Read-only; cannot modify or delete mailbox items. |
| `openid` | Non-sensitive | Cryptographic identity confirmation during the OAuth 2.0 handshake. |
| `email` | Non-sensitive | Verifies that the authenticated Gmail account matches the sender address registered in Reachy. |

> [!IMPORTANT]
> **Why broader scopes like `mail.google.com` or `gmail.modify` are NEVER used:**  
> `mail.google.com` grants full, unrestricted administrative control, including permanent message deletion. Reachy adheres strictly to the zero-trust principle of least privilege. Only the minimal permissions required for outreach and reply monitoring are requested.

### Step 5: Add Test Users (Required for "Testing" status)
1. While the app publishing status is **Testing** (default for non-verified apps), go to the **Test users** section.
2. Click **Add Users** and enter the Gmail address(es) you intend to send from with Reachy.
3. Click **Save and Continue**.

### Step 6: Create OAuth 2.0 Client Credentials
1. Go to **APIs & Services** > **Credentials**.
2. Click **+ Create Credentials** > **OAuth client ID**.
3. Set **Application type** to **Desktop app**.
4. Name it (e.g., `Reachy Desktop Client`).
5. Click **Create**.
6. A dialog displays your **Client ID** and **Client Secret**.

> [!TIP]
> **Will a "Desktop app" ID work, or do I need a different Client ID?**  
> **Yes, "Desktop app" is exactly what you need.** In Google Cloud Console, a "Desktop app" credential **is** an OAuth 2.0 Client ID. Reachy runs locally as a Python application and uses a local loopback server (`http://localhost`) to receive the OAuth redirect code. Under RFC 8252, Google strictly mandates the **Desktop app** type for localhost redirects. Never select "Web application", as web applications require verified public HTTPS domains and will reject localhost.

Copy these directly into your `.env`:
```bash
REACHY_GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
REACHY_GOOGLE_CLIENT_SECRET=GOCSPX-xxxx
```
*(Alternatively, click **Download JSON** and pass `--client-secrets /path/to/credentials.json`)*.

---

## 3. Why Google OAuth Cannot Be "Auto-Generated" Without GCP Credentials

A common question is whether an agent or CLI tool can automatically generate a Google OAuth consent screen without the user registering an app in Google Cloud.

Under the [RFC 6749 OAuth 2.0 Specification](https://datatracker.ietf.org/doc/html/rfc6749) and Google's Identity Security Model:
1. Every authorization request sent to `https://accounts.google.com/o/oauth2/v2/auth` **must** include an authorized `client_id` issued by Google Cloud.
2. If `client_id` is missing or invalid, Google's server halts immediately with:
   ```text
   Error 400: invalid_request
   Missing required parameter: client_id
   ```
3. Google does not expose an unauthenticated public API that creates OAuth 2.0 clients out of thin air, because `client_id` defines the trust boundary, verified ownership, and scope entitlements of the app.

Any tool claiming to bypass client ID registration would either be a fake mock simulation (not sending real emails through Google) or attempting phishing/credential harvesting against Google's policies. Reachy provides a direct, production-grade integration that respects security standards.

---

## 4. Revocation and Disconnect

To revoke Reachy's access to your Google account at any time:

```bash
reachy accounts disconnect --id <ACCOUNT_ID>
```

This immediately:
1. Calls Google's OAuth revocation endpoint (`https://oauth2.googleapis.com/revoke`).
2. Securely deletes the Fernet ciphertext from `account_secrets`.
3. Marks the account status as `REVOKED` in SQLite.
