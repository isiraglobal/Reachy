"""SMTP sending and IMAP reply synchronization.

Credentials are read from the encrypted secret payload, never from the
account configuration row or logs.
"""

from __future__ import annotations

import email
import imaplib
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.policy import default
from email.utils import format_datetime, make_msgid
from typing import Any, Optional

from ..models import InboundMessage, OutboundMessage, SendResult
from .base import EmailProvider


class SMTPProvider(EmailProvider):
    name = "smtp"

    def __init__(self, email_address: str, config: dict[str, Any], secret: dict[str, Any]):
        self.email_address = email_address
        self.host = config["host"]
        self.port = int(config.get("port", 587))
        self.username = config.get("username") or email_address
        self.display_name = config.get("display_name") or ""
        self.imap_host = config.get("imap_host")
        self.imap_port = int(config.get("imap_port", 993))
        self.password = secret.get("password")
        if not self.password:
            raise ValueError("SMTP password is missing from encrypted secret store")

    def send(self, message: OutboundMessage) -> SendResult:
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

        phase = "connect"
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
                smtp.ehlo()
                if smtp.has_extn("starttls") or self.port == 587:
                    smtp.starttls(context=context)
                    smtp.ehlo()
                phase = "auth"
                smtp.login(self.username, self.password)
                phase = "send"
                smtp.send_message(msg)
            return SendResult("accepted", message.message_id_header)
        except smtplib.SMTPRecipientsRefused as exc:
            return SendResult("failed", error=f"recipient refused: {exc.recipients}", retryable=False)
        except smtplib.SMTPAuthenticationError as exc:
            return SendResult("failed", error=f"SMTP authentication failed: {exc.smtp_code}", retryable=False)
        except smtplib.SMTPDataError as exc:
            retryable = 400 <= int(exc.smtp_code) < 500
            return SendResult("uncertain" if retryable else "failed", error=str(exc), retryable=retryable)
        except (smtplib.SMTPServerDisconnected, TimeoutError, ConnectionError, OSError) as exc:
            if phase == "send":
                return SendResult("uncertain", error=f"connection lost during submission: {exc}", retryable=True)
            return SendResult("failed", error=f"SMTP {phase} failed: {exc}", retryable=True)
        except Exception as exc:  # noqa: BLE001
            return SendResult("uncertain" if phase == "send" else "failed", error=str(exc), retryable=True)

    def find_by_message_id(self, message_id_header: str) -> Optional[str]:
        client = self._imap()
        if not client:
            return None
        try:
            for mailbox in ("INBOX", "Sent", "[Gmail]/Sent Mail"):
                try:
                    status, _ = client.select(mailbox, readonly=True)
                except imaplib.IMAP4.error:
                    continue
                if status != "OK":
                    continue
                status, data = client.search(None, "HEADER", "Message-ID", f'"{message_id_header}"')
                if status == "OK" and data and data[0]:
                    return data[0].split()[-1].decode()
            return None
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def fetch_replies(self, since: Optional[datetime] = None) -> list[InboundMessage]:
        client = self._imap()
        if not client:
            return []
        messages: list[InboundMessage] = []
        try:
            client.select("INBOX", readonly=True)
            criterion = "(UNSEEN)"
            if since:
                criterion = f'(UNSEEN SINCE {since.strftime("%d-%b-%Y")})'
            status, data = client.search(None, criterion)
            if status != "OK" or not data or not data[0]:
                return []
            for uid in data[0].split():
                status, payload = client.fetch(uid, "(RFC822)")
                if status != "OK":
                    continue
                raw = next((item[1] for item in payload if isinstance(item, tuple)), None)
                if not raw:
                    continue
                parsed = email.message_from_bytes(raw, policy=default)
                from_email = (parsed.get("From") or "").lower()
                if self.email_address.lower() in from_email:
                    continue
                body = _extract_body(parsed)
                references = (parsed.get("References") or "").split()
                messages.append(
                    InboundMessage(
                        provider_id=parsed.get("Message-ID") or f"imap-{uid.decode()}",
                        from_email=from_email,
                        subject=parsed.get("Subject") or "",
                        body=body,
                        received_at=(parsed.get("Date") or datetime.now().isoformat()),
                        message_id_header=parsed.get("Message-ID"),
                        in_reply_to=parsed.get("In-Reply-To"),
                        references=references,
                        headers={k: str(v) for k, v in parsed.items()},
                        raw={"uid": uid.decode()},
                    )
                )
        finally:
            try:
                client.logout()
            except Exception:
                pass
        return messages

    def check(self) -> tuple[bool, str]:
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
                smtp.ehlo()
                if smtp.has_extn("starttls") or self.port == 587:
                    smtp.starttls(context=context)
                    smtp.ehlo()
                smtp.login(self.username, self.password)
            return True, "SMTP authentication succeeded"
        except Exception as exc:  # noqa: BLE001
            return False, f"SMTP check failed: {exc.__class__.__name__}: {exc}"

    def _imap(self) -> Optional[imaplib.IMAP4_SSL]:
        if not self.imap_host:
            return None
        try:
            client = imaplib.IMAP4_SSL(self.imap_host, self.imap_port, timeout=30)
            client.login(self.username, self.password)
            return client
        except Exception:
            return None


def _extract_body(parsed) -> str:
    if parsed.is_multipart():
        for part in parsed.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(
                part.get("Content-Disposition") or ""
            ):
                try:
                    return part.get_content()
                except Exception:
                    continue
        for part in parsed.walk():
            if part.get_content_type() == "text/html":
                try:
                    return _strip_html(part.get_content())
                except Exception:
                    continue
        return ""
    try:
        content = parsed.get_content()
        if parsed.get_content_type() == "text/html":
            return _strip_html(str(content))
        return str(content)
    except Exception:
        return ""


def _strip_html(html: str) -> str:
    try:
        import bs4

        return bs4.BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    except Exception:
        return html
