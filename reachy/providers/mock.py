"""Test provider. Never touches the network or real recipients."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Optional

from ..models import InboundMessage, OutboundMessage, SendResult
from .base import EmailProvider


class MockProvider(EmailProvider):
    name = "mock"

    def __init__(self):
        self.sent: list[OutboundMessage] = []
        self.outcomes: deque[SendResult] = deque()
        self.found: dict[str, str] = {}
        self.replies: list[InboundMessage] = []
        self.fail_check: Optional[str] = None

    def queue_outcome(self, outcome: SendResult) -> None:
        self.outcomes.append(outcome)

    def queue_reply(self, reply: InboundMessage) -> None:
        self.replies.append(reply)

    def send(self, message: OutboundMessage) -> SendResult:
        if self.outcomes:
            outcome = self.outcomes.popleft()
            if outcome.status == "accepted":
                self.sent.append(message)
                self.found[message.message_id_header] = outcome.provider_message_id or f"mock-{len(self.sent)}"
            return outcome
        self.sent.append(message)
        provider_id = f"mock-{len(self.sent)}"
        self.found[message.message_id_header] = provider_id
        return SendResult("accepted", provider_id)

    def find_by_message_id(self, message_id_header: str) -> Optional[str]:
        return self.found.get(message_id_header)

    def fetch_replies(self, since: Optional[datetime] = None) -> list[InboundMessage]:
        return list(self.replies)

    def check(self) -> tuple[bool, str]:
        if self.fail_check:
            return False, self.fail_check
        return True, "mock provider ready"
