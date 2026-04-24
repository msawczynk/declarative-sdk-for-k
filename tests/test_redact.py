from keeper_sdk.core.redact import REDACTED, redact


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


def test_redact_empty_secret_left_alone() -> None:
    # empty string / None count as "not a live secret" to avoid noise
    assert redact({"password": ""}) == {"password": ""}


def test_redact_bearer_token_string() -> None:
    value = "Authorization: Bearer abc.DEF_123-xyz"
    assert redact(value) == f"Authorization: {REDACTED}"


def test_redact_jwt_string() -> None:
    value = "token=eyJabcDEF_123-.eyJpayload_456-abc.signature_789-xyz"
    assert redact(value) == f"token={REDACTED}"


def test_redact_ksm_one_time_token_string() -> None:
    value = "launch EU:AbCdEfGhIjKlMnOpQrStUvwxYZ_1234 now"
    assert redact(value) == f"launch {REDACTED} now"
