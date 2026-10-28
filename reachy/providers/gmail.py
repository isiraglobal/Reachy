"""Gmail delivery through the official Gmail API.

The Gmail web interface is never automated. The API is used with least-privilege
scopes (``gmail.send`` and ``gmail.readonly``). Google Cloud OAuth client
configuration and, for commercial distribution, Google verification are the
customer's responsibility.
"""

from __future__ import annotations

import base64
from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime
from typing import Any, Callable, Optional

from ..models import InboundMessage, OutboundMessage, SendResult
from .base import EmailProvider


class GmailProvider(EmailProvider):
    name = "gmail"

    def __init__(
        self,
        email_address: str,
        config: dict[str, Any],
        token_payload: dict[str, Any],
        oauth,
        persist_token: Optional[Callable[[dict[str, Any]], None]] = None,
    ):
        self.email_address = email_address
        self.display_name = config.get("display_name") or ""
        self.token_payload = token_payload
        self.oauth = oauth
        self.persist_token = persist_token
        self._service = None

    def _api(self):
        if self._service is not None:
            return self._service
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError("Gmail support requires: pip install 'reachy[gmail]'") from exc
        credentials = self.oauth.credentials(self.token_payload, refresh=True)
        if self.persist_token:
            self.persist_token(self.token_payload)
        self._service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        return self._service

    def send(self, message: OutboundMessage) -> SendResult:
        from email.utils import make_msgid  # noqa: F401  (import kept for callers)

        msg = EmailMessage()
        sender = f"{self.display_name} <{self.email_address}>" if self.display_name else self.email_address
        msg["From"] = sender
        msg["To"] = message.to_email
        msg["Subject"] = message.subject
        msg["Message-ID"] = message.message_id_header
        msg["Date"] = format_datetime(datetime.now().astimezone())
        if message.reply_to:
            msg["Reply-To"] = message.reply_to
        for key, value in message.headers.items():
            msg[key] = value
        msg.set_content(message.body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

        try:
            result = (
                self._api()
                .users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute()
            )
            return SendResult("accepted", result.get("id"))
        except Exception as exc:  # noqa: BLE001
            status = _http_status(exc)
            if status is None:
                return SendResult("uncertain", error=f"Gmail transport error: {exc}", retryable=True)
            if status == 429 or 500 <= status < 600:
                return SendResult("uncertain", error=f"Gmail temporary error {status}", retryable=True)
            return SendResult("failed", error=f"Gmail API error {status}: {exc}", retryable=False)

    def find_by_message_id(self, message_id_header: str) -> Optional[str]:
        clean = message_id_header.strip().strip("<>")
        for query in (f"rfc822msgid:{message_id_header}", f"rfc822msgid:{clean}"):
            try:
                result = (
                    self._api()
                    .users()
                    .messages()
                    .list(userId="me", q=query, maxResults=1)
                    .execute()
                )
                messages = result.get("messages") or []
                if messages:
                    return messages[0]["id"]
            except Exception:
                continue
        return None

    def fetch_replies(self, since: Optional[datetime] = None) -> list[InboundMessage]:
        query = "in:inbox -from:me"
        if since:
            query += f" after:{int(since.timestamp())}"
        try:
            result = (
                self._api()
                .users()
                .messages()
                .list(userId="me", q=query, maxResults=100)
                .execute()
            )
        except Exception:
            return []
        replies: list[InboundMessage] = []
        for item in result.get("messages") or []:
            try:
                full = (
                    self._api()
                    .users()
                    .messages()
                    .get(userId="me", id=item["id"], format="full")
                    .execute()
                )
                replies.append(_to_inbound(full))
            except Exception:
                continue
        return replies

    def check(self) -> tuple[bool, str]:
        try:
            profile = self._api().users().getProfile(userId="me").execute()
            return True, f"Gmail API connected as {profile.get('emailAddress', self.email_address)}"
        except Exception as exc:  # noqa: BLE001
            return False, f"Gmail check failed: {exc.__class__.__name__}: {exc}"


def _http_status(exc: Exception) -> Optional[int]:
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    if status is None:
        return None
    try:
        return int(status)
    except (TypeError, ValueError):
        return None


def _headers_map(payload: dict[str, Any]) -> dict[str, str]:
    return {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers", [])}


def _to_inbound(message: dict[str, Any]) -> InboundMessage:
    payload = message.get("payload", {})
    headers = _headers_map(payload)
    references = headers.get("references", "").split()
    body = _extract_gmail_body(payload)
    return InboundMessage(
        provider_id=message.get("id", ""),
        from_email=(headers.get("from") or "").lower(),
        subject=headers.get("subject") or "",
        body=body,
        received_at=headers.get("date") or datetime.now().isoformat(),
        message_id_header=headers.get("message-id"),
        in_reply_to=headers.get("in-reply-to"),
        references=references,
        headers=headers,
        raw={"threadId": message.get("threadId"), "labelIds": message.get("labelIds", [])},
    )


def _extract_gmail_body(payload: dict[str, Any]) -> str:
    plain = _find_part(payload, "text/plain")
    if plain:
        return plain
    html = _find_part(payload, "text/html")
    if html:
        try:
            import bs4

            return bs4.BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        except Exception:
            return html
    return ""


def _find_part(payload: dict[str, Any], mime: str) -> Optional[str]:
    if payload.get("mimeType") == mime:
        data = payload.get("body", {}).get("data")
        if data:
            try:
                return base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="ignore")
            except Exception:
                return None
    for part in payload.get("parts") or []:
        found = _find_part(part, mime)
        if found:
            return found
    return None
