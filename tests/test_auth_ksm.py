from __future__ import annotations

from typing import Any

import pytest

from keeper_sdk.auth import KsmLoginHelper
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.providers.commander_cli import CommanderCliProvider
from keeper_sdk.secrets import KsmLoginCreds


def test_ksm_login_helper_init_reads_record_uid_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KEEPER_SDK_KSM_CREDS_RECORD_UID", "ENVUID123456")

    helper = KsmLoginHelper()

    assert helper.record_uid == "ENVUID123456"


def test_ksm_login_helper_init_explicit_record_uid_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KEEPER_SDK_KSM_CREDS_RECORD_UID", "ENVUID123456")

    helper = KsmLoginHelper(record_uid="ARGUID123456")

    assert helper.record_uid == "ARGUID123456"


def test_ksm_login_helper_init_missing_uid_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KEEPER_SDK_KSM_CREDS_RECORD_UID", raising=False)

    with pytest.raises(CapabilityError) as exc_info:
        KsmLoginHelper()

    assert exc_info.value.next_action is not None
    assert "set KEEPER_SDK_KSM_CREDS_RECORD_UID" in exc_info.value.next_action


def test_ksm_login_helper_load_keeper_creds_flows_values_and_login_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def fake_load(record_uid: str, **kwargs: Any) -> KsmLoginCreds:
        calls["record_uid"] = record_uid
        calls.update(kwargs)
        return KsmLoginCreds(
            email="operator@example.invalid",
            password="password-value",
            totp_secret="JBSWY3DPEHPK3PXP",
            config_path="/tmp/keeper.json",
            server="keepersecurity.eu",
        )

    monkeypatch.setattr("keeper_sdk.auth.helper.load_keeper_login_from_ksm", fake_load)
    monkeypatch.setenv("KEEPER_SDK_KSM_CREDS_RECORD_UID", "ENVUID123456")
    monkeypatch.setenv("KEEPER_SDK_KSM_CONFIG", "/tmp/ksm-config.json")
    monkeypatch.setenv("KEEPER_CONFIG", "/tmp/keeper.json")
    monkeypatch.setenv("KEEPER_SERVER", "keepersecurity.eu")

    creds = KsmLoginHelper().load_keeper_creds()

    assert creds == {
        "email": "operator@example.invalid",
        "password": "password-value",
        "totp_secret": "JBSWY3DPEHPK3PXP",
        "config_path": "/tmp/keeper.json",
        "server": "keepersecurity.eu",
    }
    assert calls["record_uid"] == "ENVUID123456"
    assert calls["config_path"] == "/tmp/ksm-config.json"
    assert calls["config_path_for_login"] == "/tmp/keeper.json"
    assert calls["server"] == "keepersecurity.eu"


def test_ksm_login_helper_field_override_env_vars_reach_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def fake_load(record_uid: str, **kwargs: Any) -> KsmLoginCreds:
        calls["record_uid"] = record_uid
        calls.update(kwargs)
        return KsmLoginCreds(
            email="operator@example.invalid",
            password="password-value",
            totp_secret="JBSWY3DPEHPK3PXP",
        )

    monkeypatch.setattr("keeper_sdk.auth.helper.load_keeper_login_from_ksm", fake_load)
    monkeypatch.setenv("KEEPER_SDK_KSM_CREDS_RECORD_UID", "ENVUID123456")
    monkeypatch.setenv("KEEPER_SDK_KSM_LOGIN_FIELD", "custom-login")
    monkeypatch.setenv("KEEPER_SDK_KSM_PASSWORD_FIELD", "custom-password")
    monkeypatch.setenv("KEEPER_SDK_KSM_TOTP_FIELD", "custom-totp")
    monkeypatch.delenv("KEEPER_CONFIG", raising=False)
    monkeypatch.delenv("KEEPER_SERVER", raising=False)

    _ = KsmLoginHelper().load_keeper_creds()

    assert calls["login_field"] == "custom-login"
    assert calls["password_field"] == "custom-password"
    assert calls["totp_field"] == "custom-totp"


def test_ksm_login_helper_keeper_login_calls_shared_commander_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}
    params = object()

    def fake_perform(
        email: str,
        password: str,
        totp_secret: str,
        *,
        config_path: str,
        server: str | None,
    ) -> object:
        calls.update(
            {
                "email": email,
                "password": password,
                "totp_secret": totp_secret,
                "config_path": config_path,
                "server": server,
            }
        )
        return params

    monkeypatch.setattr("keeper_sdk.auth.helper._perform_commander_login", fake_perform)

    result = KsmLoginHelper(record_uid="ARGUID123456").keeper_login(
        "operator@example.invalid",
        "password-value",
        "JBSWY3DPEHPK3PXP",
        config_path="/tmp/keeper.json",
        server="keepersecurity.eu",
    )

    assert result is params
    assert calls == {
        "email": "operator@example.invalid",
        "password": "password-value",
        "totp_secret": "JBSWY3DPEHPK3PXP",
        "config_path": "/tmp/keeper.json",
        "server": "keepersecurity.eu",
    }


def test_provider_dispatches_ksm_sentinel_to_in_tree_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which",
        lambda _bin: "/usr/local/bin/keeper",
    )
    monkeypatch.setenv("KEEPER_SDK_LOGIN_HELPER", "ksm")
    params = object()

    class FakeKsmLoginHelper:
        calls = 0

        def __init__(self) -> None:
            self.__class__.calls += 1

        def load_keeper_creds(self) -> dict[str, str]:
            return {
                "email": "operator@example.invalid",
                "password": "password-value",
                "totp_secret": "JBSWY3DPEHPK3PXP",
            }

        def keeper_login(
            self,
            email: str,
            password: str,
            totp_secret: str,
            **kwargs: Any,
        ) -> object:
            assert email == "operator@example.invalid"
            assert password == "password-value"
            assert totp_secret == "JBSWY3DPEHPK3PXP"
            assert kwargs == {}
            return params

    monkeypatch.setattr("keeper_sdk.auth.KsmLoginHelper", FakeKsmLoginHelper)
    provider = CommanderCliProvider(folder_uid="folder-uid")

    assert provider._get_keeper_params() is params
    assert FakeKsmLoginHelper.calls == 1
