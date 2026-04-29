"""Secret redaction for plan/diff rendering and logs."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from typing import Any, TypeAlias

# Field substrings that must never be rendered.
_SECRET_TOKENS = (
    "password",
    "secret",
    "api key",
    "api_key",
    "credential",
    "private_key",
    "private_pem_key",
    "client_secret",
    "aws_secret",
    "service_account_key",
    "admin_private_key",
    "otp",
)

_SECRET_FIELD_TYPES = {
    "password",
    "securityquestion",
    "secretquestion",
    "pincode",
    "secret",
    "keypair",
    "bankaccount",
    "paymentcard",
    "fileref",
}

REDACTED = "***redacted***"
_INLINE_REDACTED = "***"

_Replacement: TypeAlias = str | Callable[[re.Match[str]], str]


def _mask_token(token: str) -> str:
    if token.startswith("eyJ") and "." in token:
        return f"{token.split('.', 1)[0]}{_INLINE_REDACTED}"
    return f"{token[:4]}{_INLINE_REDACTED}"


def _mask_base32(secret: str) -> str:
    if len(secret) <= 4:
        return _INLINE_REDACTED
    return f"{secret[:2]}{_INLINE_REDACTED}{secret[-2:]}"


def _redact_auth(match: re.Match[str]) -> str:
    return f"{match.group(1)}{_mask_token(match.group(2))}"


def _redact_jwt(match: re.Match[str]) -> str:
    return f"{match.group(1)[:6]}{_INLINE_REDACTED}"


def _redact_ksm_url(match: re.Match[str]) -> str:
    suffix = match.group("suffix")
    if not suffix:
        return match.group(0)
    return f"{match.group('host')}/{_INLINE_REDACTED}"


def _redact_otpauth_secret(match: re.Match[str]) -> str:
    return f"{match.group(1)}{_mask_base32(match.group(2))}"


def _redact_env_assignment(match: re.Match[str]) -> str:
    return f"{match.group(1)}{_INLINE_REDACTED}"


def _redact_base32(match: re.Match[str]) -> str:
    return _mask_base32(match.group(0))


_PATTERNS: tuple[tuple[re.Pattern[str], _Replacement], ...] = (
    (
        re.compile(r"(?i)\b(otpauth://[^\s;]*?[?&]secret=)([A-Z2-7]+)(?=(&|[\s;]|$))"),
        _redact_otpauth_secret,
    ),
    (
        re.compile(r"(?i)\b(?P<host>ksm://[^/\s?#;]+)(?P<suffix>(?:/[^\s?;]*)?(?:\?[^\s;]*)?)"),
        _redact_ksm_url,
    ),
    (
        re.compile(r"(?i)\b(?P<host>keeper://[^/\s?#;]+)(?P<suffix>(?:/[^\s?;]*)?(?:\?[^\s;]*)?)"),
        _redact_ksm_url,
    ),
    (
        re.compile(r"\b(KEEPER_(?:PASSWORD|TOTP_SECRET|EMAIL)=)([^\s;]+)"),
        _redact_env_assignment,
    ),
    (
        re.compile(r"(?i)\b((?:Authorization:\s*)?(?:Bearer|Token)\s+)([A-Za-z0-9._~+/=-]{3,})"),
        _redact_auth,
    ),
    (
        re.compile(r"\b(eyJ[A-Za-z0-9_-]*)(?:\.[A-Za-z0-9_-]+){2}\b"),
        _redact_jwt,
    ),
    (
        re.compile(r"\b(?:US|EU|AU|JP|CA|GOV):[A-Za-z0-9_-]{20,}\b"),
        REDACTED,
    ),
    (
        re.compile(r"\b[A-Z2-7]{16,}\b"),
        _redact_base32,
    ),
)


def _is_secret(key: str) -> bool:
    lower = key.lower()
    return any(token in lower for token in _SECRET_TOKENS)


def _field_type_key(value: Any) -> str:
    return str(value or "").replace("_", "").casefold()


def _is_secret_typed_field(value: dict[Any, Any]) -> bool:
    field_type = _field_type_key(value.get("type"))
    if field_type in _SECRET_FIELD_TYPES:
        return True
    for label_key in ("label", "name", "key"):
        label = value.get(label_key)
        if isinstance(label, str) and _is_secret(label):
            return True
    return False


def _redact_field_value(value: Any) -> Any:
    if value in (None, ""):
        return value
    if isinstance(value, list):
        return [REDACTED if item not in (None, "") else item for item in value]
    return REDACTED


def _redact_string(value: str) -> str:
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _redact_secret_value(value: Any) -> Any:
    if value in (None, "", "<redacted>", REDACTED):
        return value
    return REDACTED


def redact(value: Any) -> Any:
    """Deep-copy with any secret-flavored field replaced by the sentinel."""
    if isinstance(value, dict):
        if _is_secret_typed_field(value) and "value" in value:
            return {
                k: (_redact_field_value(v) if k == "value" else redact(v)) for k, v in value.items()
            }
        return {
            k: (_redact_secret_value(v) if _is_secret(k) else redact(v)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return _redact_string(value)
    return value


def redact_lines(lines: Iterable[str]) -> Iterator[str]:
    """Yield redacted text lines without materializing the full input."""
    for line in lines:
        yield _redact_string(line)
