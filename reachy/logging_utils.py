"""Structured logging and secret redaction.

Logs carry identifiers (campaign/message/account IDs), never message bodies,
tokens, passwords, or authorization headers by default.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Mapping, MutableMapping

SECRET_KEYS = {
    "password",
    "passwd",
    "secret",
    "client_secret",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "authorization",
    "auth",
    "cookie",
    "set-cookie",
    "private_key",
    "smtp_password",
    "imap_password",
}

_REDACTED = "[REDACTED]"

_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)((?:password|secret|token|api[_-]?key)\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
]


def redact(value: Any) -> Any:
    """Recursively redact secret-looking keys and values."""
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in SECRET_KEYS:
                out[key] = _REDACTED
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_text(text: str) -> str:
    result = text
    for pattern in _PATTERNS:
        result = pattern.sub(
            lambda m: (m.group(1) if m.groups() else "") + _REDACTED, result
        )
    return result


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if record.args:
            record.args = tuple(
                redact_text(a) if isinstance(a, str) else a for a in record.args
            )
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: MutableMapping[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        for key in ("account_id", "campaign_id", "message_id", "reply_id", "job"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(path=None, level: int = logging.INFO, json_logs: bool = True) -> logging.Logger:
    root = logging.getLogger("reachy")
    if getattr(root, "_reachy_configured", False):
        return root
    root.setLevel(level)
    root.propagate = False
    formatter: logging.Formatter = (
        JsonFormatter() if json_logs else logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.addFilter(RedactionFilter())
    root.addHandler(stream)
    if path:
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(RedactionFilter())
        root.addHandler(file_handler)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    root._reachy_configured = True  # type: ignore[attr-defined]
    return root
