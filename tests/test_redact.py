import re

import pytest

from keeper_sdk.core.redact import _PATTERNS, REDACTED, redact, redact_lines


def test_redact_top_level_password() -> None:
    out = redact({"title": "ok", "password": "secret"})
    assert out["password"] == REDACTED
    assert out["title"] == "ok"


def test_redact_nested() -> None:
    out = redact(
        {
            "resources": [
                {
                    "title": "r",
                    "pam_settings": {"connection": {"administrative_credentials_uid_ref": "x"}},
                },
            ],
            "aws_secret_access_key": "SUPER",
            "notes": "",
        }
    )
    assert out["aws_secret_access_key"] == REDACTED
    assert out["resources"][0]["title"] == "r"


def test_redact_sequence_types() -> None:
    assert redact(("Bearer abcd1234567890", ["KEEPER_PASSWORD=hunter2"], 3)) == (
        "Bearer abcd***",
        ["KEEPER_PASSWORD=***"],
        3,
    )


def test_redact_empty_secret_left_alone() -> None:
    # empty string / None count as "not a live secret" to avoid noise
    assert redact({"password": ""}) == {"password": ""}


def test_patterns_are_exported_for_introspection() -> None:
    assert _PATTERNS
    assert all(isinstance(pattern, re.Pattern) for pattern, _replacement in _PATTERNS)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Authorization: Bearer eyJ.X.Y", "Authorization: Bearer eyJ***"),
        ("bearer abcd1234567890", "bearer abcd***"),
        ("Token zyx987opaque", "Token zyx9***"),
        ("KEEPER_PASSWORD=hunter2", "KEEPER_PASSWORD=***"),
        ("KEEPER_TOTP_SECRET=JBSWY3DPEHPK3PXP", "KEEPER_TOTP_SECRET=***"),
        ("KEEPER_EMAIL=a@b.com", "KEEPER_EMAIL=***"),
        (
            "Hello otpauth://totp/Account?secret=JBSWY3DPEHPK3PXP&issuer=Foo",
            "Hello otpauth://totp/Account?secret=JB***XP&issuer=Foo",
        ),
        (
            "Random base32-looking JBSWY3DPEHPK3PXP nope",
            "Random base32-looking JB***XP nope",
        ),
        (
            "load ksm://keeper.example/records/abc?field=password&title=x now",
            "load ksm://keeper.example/*** now",
        ),
        (
            "load keeper://keeper.example/records/abc?field=password&title=x now",
            "load keeper://keeper.example/*** now",
        ),
        (
            "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature done",
            "jwt eyJhbG*** done",
        ),
        (
            "launch EU:AbCdEfGhIjKlMnOpQrStUvwxYZ_1234 now",
            f"launch {REDACTED} now",
        ),
    ],
)
def test_redact_string_patterns(value: str, expected: str) -> None:
    assert redact(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "Record UID ABC123def456GHI789jkl0 is shareable",
        "Authorization: Basic abcdefghijklmnop",
        "bearer",
        "token=abcd1234567890",
        "KEEPER_USERNAME=admin",
        "Hello otpauth://totp/Account?issuer=Foo",
        "Random base32-looking JBSWY3DPEHPK3PX nope",
        "Random base32-looking JBSWY3DPEHPK3PX9 nope",
        "ksm-ish https://keeper.example/record?query=secret",
        "ksm://keeper.example",
    ],
)
def test_redact_string_negative_cases(value: str) -> None:
    assert redact(value) == value


def test_redact_mixed_patterns_preserves_structure() -> None:
    value = "Mixed: Bearer abc; otpauth://totp/Account?secret=DEF; KEEPER_EMAIL=a@b.com"
    assert redact(value) == (
        "Mixed: Bearer abc***; otpauth://totp/Account?secret=***; KEEPER_EMAIL=***"
    )


def test_redact_lines_streams_redacted_strings() -> None:
    assert list(redact_lines(["Bearer abcd1234567890\n", "safe\n"])) == [
        "Bearer abcd***\n",
        "safe\n",
    ]
