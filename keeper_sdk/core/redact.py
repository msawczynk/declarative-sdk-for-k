"""Secret redaction for plan/diff rendering and logs."""

from __future__ import annotations

from typing import Any

# Field substrings that must never be rendered.
_SECRET_TOKENS = (
    "password",
    "secret",
    "private_key",
    "private_pem_key",
    "client_secret",
    "aws_secret",
    "service_account_key",
    "admin_private_key",
    "otp",
)

REDACTED = "***redacted***"


def _is_secret(key: str) -> bool:
    lower = key.lower()
    return any(token in lower for token in _SECRET_TOKENS)


def redact(value: Any) -> Any:
    """Deep-copy with any secret-flavored field replaced by the sentinel."""
    if isinstance(value, dict):
        return {
            k: (REDACTED if _is_secret(k) and v not in (None, "") else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value
