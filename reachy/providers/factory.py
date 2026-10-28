"""Construct providers from stored account records."""

from __future__ import annotations

import json
from typing import Any, Optional

from ..db import Database
from ..oauth import GoogleOAuth, TokenCipher, TokenStore
from .base import EmailProvider, ProviderError
from .gmail import GmailProvider
from .mock import MockProvider
from .smtp import SMTPProvider


def account_config(account: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = json.loads(account.get("config_json") or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def build_provider(
    db: Database,
    account: dict[str, Any],
    cipher: Optional[TokenCipher] = None,
    oauth: Optional[GoogleOAuth] = None,
    mock: Optional[MockProvider] = None,
) -> EmailProvider:
    provider = account["provider"]
    config = account_config(account)
    if provider == "mock":
        return mock or MockProvider()
    if provider == "smtp":
        if cipher is None:
            raise ProviderError("encryption key is required to read SMTP credentials")
        secret = TokenStore(db).load(int(account["id"]), cipher)
        if not secret:
            raise ProviderError("SMTP credentials are missing; re-attach the account")
        return SMTPProvider(account["email"], config, secret)
    if provider == "gmail":
        if cipher is None:
            raise ProviderError("encryption key is required to read Gmail tokens")
        oauth = oauth or GoogleOAuth(cipher)
        payload = TokenStore(db).load(int(account["id"]), cipher)
        if not payload:
            raise ProviderError("Gmail token is missing; reconnect the account")
        account_id = int(account["id"])

        def persist(token_payload: dict[str, Any]) -> None:
            TokenStore(db).store(account_id, token_payload, cipher)

        return GmailProvider(account["email"], config, payload, oauth, persist_token=persist)
    raise ProviderError(f"unsupported provider: {provider}")


def provider_check(db: Database, account: dict[str, Any], **kwargs) -> tuple[bool, str]:
    try:
        provider = build_provider(db, account, **kwargs)
        return provider.check()
    except Exception as exc:  # noqa: BLE001
        return False, f"{exc.__class__.__name__}: {exc}"
