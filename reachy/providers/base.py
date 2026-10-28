"""Provider abstraction.

Adding a delivery method must not require changing the campaign engine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from ..models import InboundMessage, OutboundMessage, SendResult


class ProviderError(RuntimeError):
    pass


class EmailProvider(ABC):
    name = "base"

    @abstractmethod
    def send(self, message: OutboundMessage) -> SendResult:
        ...

    @abstractmethod
    def find_by_message_id(self, message_id_header: str) -> Optional[str]:
        """Return the provider ID if the message was accepted, else None.

        ``None`` means "not found or inconclusive"; callers must not treat it
        as proof of failure until a grace period has elapsed.
        """

    @abstractmethod
    def fetch_replies(self, since: Optional[datetime] = None) -> list[InboundMessage]:
        ...

    def check(self) -> tuple[bool, str]:
        return True, "ok"

    def close(self) -> None:
        return None
