"""Encrypted token storage and Google OAuth lifecycle.

- Tokens are encrypted with Fernet before touching SQLite.
- The key comes from ``REACHY_SECRET_KEY`` (urlsafe base64) or a 0600 key file.
- Disconnect revokes the token with Google and deletes the local secret.
- No Google password is ever requested or stored.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .db import Database, utcnow

GMAIL_SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

REVOKE_URL = "https://oauth2.googleapis.com/revoke"


class OAuthError(RuntimeError):
    pass


class OAuthRevokedError(OAuthError):
    pass


class TokenCipher:
    def __init__(self, key: Optional[bytes] = None, key_path: Optional[str | Path] = None):
        from cryptography.fernet import Fernet

        if key is None:
            env_key = os.environ.get("REACHY_SECRET_KEY")
            if env_key:
                key = env_key.encode("utf-8")
            elif key_path and Path(key_path).exists():
                key = Path(key_path).read_bytes().strip()
            else:
                key = Fernet.generate_key()
                if key_path:
                    path = Path(key_path)
                    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(key)
                    try:
                        os.chmod(path, 0o600)
                    except OSError:
                        pass
        try:
            self._fernet = Fernet(key)
        except Exception as exc:  # noqa: BLE001
            raise OAuthError(f"invalid REACHY_SECRET_KEY / key file: {exc}") from exc

    def encrypt(self, payload: dict[str, Any]) -> bytes:
        return self._fernet.encrypt(json.dumps(payload, sort_keys=True).encode("utf-8"))

    def decrypt(self, token: bytes) -> dict[str, Any]:
        return json.loads(self._fernet.decrypt(token).decode("utf-8"))


class TokenStore:
    def __init__(self, db: Database):
        self.db = db

    def store(self, account_id: int, payload: dict[str, Any], cipher: TokenCipher) -> None:
        self.db.execute(
            """INSERT INTO account_secrets(account_id, ciphertext, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(account_id) DO UPDATE SET ciphertext=excluded.ciphertext,
                   updated_at=excluded.updated_at""",
            (account_id, cipher.encrypt(payload), utcnow()),
        )

    def load(self, account_id: int, cipher: TokenCipher) -> Optional[dict[str, Any]]:
        row = self.db.fetchone("SELECT ciphertext FROM account_secrets WHERE account_id = ?", (account_id,))
        return cipher.decrypt(row["ciphertext"]) if row else None

    def delete(self, account_id: int) -> None:
        self.db.execute("DELETE FROM account_secrets WHERE account_id = ?", (account_id,))


class GoogleOAuth:
    def __init__(
        self,
        cipher: TokenCipher,
        scopes: Optional[list[str]] = None,
        revoke_func: Optional[Callable[[str], bool]] = None,
    ):
        self.cipher = cipher
        self.scopes = scopes or GMAIL_SCOPES
        self._revoke_func = revoke_func or self._revoke_http

    # ------------------------------------------------------------- authorize
    def authorize(
        self,
        db: Database,
        account_id: int,
        client_secrets_path: str | Path,
        port: int = 0,
        open_browser: bool = False,
    ) -> dict[str, Any]:
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:  # pragma: no cover - optional extra
            raise OAuthError(
                "Gmail OAuth requires the 'gmail' extra: pip install 'reachy[gmail]'"
            ) from exc
        if not Path(client_secrets_path).exists():
            raise OAuthError(f"Google OAuth client secrets file not found: {client_secrets_path}")
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secrets_path), scopes=self.scopes
        )
        credentials = flow.run_local_server(
            port=port,
            open_browser=open_browser,
            authorization_prompt_message="Open this URL to authorize Reachy: {url}",
            success_message="Reachy authorization complete. You can close this window.",
        )
        payload = self._payload_from_credentials(credentials)
        TokenStore(db).store(account_id, payload, self.cipher)
        return payload

    def _payload_from_credentials(self, credentials) -> dict[str, Any]:
        expiry = getattr(credentials, "expiry", None)
        return {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": getattr(credentials, "token_uri", "https://oauth2.googleapis.com/token"),
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes or self.scopes),
            "expiry": expiry.isoformat() if isinstance(expiry, datetime) else None,
            "email": getattr(credentials, "id_token", None),  # informational only
        }

    # ------------------------------------------------------------- lifecycle
    def credentials(self, payload: dict[str, Any], refresh: bool = True):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
        except ImportError as exc:  # pragma: no cover - optional extra
            raise OAuthError(
                "Gmail OAuth requires the 'gmail' extra: pip install 'reachy[gmail]'"
            ) from exc
        credentials = Credentials(
            token=payload.get("token"),
            refresh_token=payload.get("refresh_token"),
            token_uri=payload.get("token_uri") or "https://oauth2.googleapis.com/token",
            client_id=payload.get("client_id"),
            client_secret=payload.get("client_secret"),
            scopes=payload.get("scopes"),
        )
        if refresh and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except Exception as exc:  # noqa: BLE001
                if exc.__class__.__name__ in {"RefreshError", "TransportError"}:
                    raise OAuthRevokedError(f"Google token refresh failed: {exc}") from exc
                raise
            payload.update(
                {
                    "token": credentials.token,
                    "refresh_token": credentials.refresh_token or payload.get("refresh_token"),
                    "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
                }
            )
        return credentials

    def refresh(self, db: Database, account_id: int) -> dict[str, Any]:
        payload = TokenStore(db).load(account_id, self.cipher)
        if not payload:
            raise OAuthError(f"no OAuth token stored for account {account_id}")
        try:
            self.credentials(payload, refresh=True)
        except OAuthRevokedError:
            db.execute(
                "UPDATE accounts SET status='ERROR', last_error=?, updated_at=? WHERE id=?",
                ("OAuth refresh failed; re-authorization required", utcnow(), account_id),
            )
            raise
        TokenStore(db).store(account_id, payload, self.cipher)
        return payload

    def revoke(self, token: str) -> bool:
        return self._revoke_func(token)

    def _revoke_http(self, token: str) -> bool:
        if not token:
            return False
        data = urllib.parse.urlencode({"token": token}).encode("utf-8")
        request = urllib.request.Request(
            REVOKE_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return 200 <= response.status < 300
        except Exception:
            return False

    def disconnect(self, db: Database, account_id: int) -> bool:
        row = db.fetchone("SELECT email FROM accounts WHERE id = ?", (account_id,))
        if not row:
            raise KeyError(f"account {account_id} not found")
        payload = TokenStore(db).load(account_id, self.cipher)
        revoked = False
        if payload:
            token = payload.get("refresh_token") or payload.get("token")
            if token:
                revoked = self.revoke(str(token))
        TokenStore(db).delete(account_id)
        db.execute(
            "UPDATE accounts SET status='REVOKED', revoked_at=?, updated_at=? WHERE id=?",
            (utcnow(), utcnow(), account_id),
        )
        db.audit("user", "account.disconnected", "account", account_id, {"token_revoked": revoked})
        return revoked


def token_expired(payload: dict[str, Any]) -> bool:
    expiry = payload.get("expiry")
    if not expiry:
        return True
    try:
        parsed = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed <= datetime.now(timezone.utc)
