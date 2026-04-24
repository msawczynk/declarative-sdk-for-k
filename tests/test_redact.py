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
