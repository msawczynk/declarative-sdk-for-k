from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from keeper_sdk.auth.helper import EnvLoginHelper, _AutoLoginUi
from keeper_sdk.core.errors import CapabilityError


def test_env_login_helper_reads_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / "keeper.json"
    monkeypatch.setenv("KEEPER_EMAIL", "operator@example.com")
    monkeypatch.setenv("KEEPER_PASSWORD", "secret")
    monkeypatch.setenv("KEEPER_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    monkeypatch.setenv("KEEPER_SERVER", "keepersecurity.eu")
    monkeypatch.setenv("KEEPER_CONFIG", str(config_path))

    creds = EnvLoginHelper().load_keeper_creds()

    assert creds == {
        "email": "operator@example.com",
        "password": "secret",
        "totp_secret": "JBSWY3DPEHPK3PXP",
        "server": "keepersecurity.eu",
        "config_path": str(config_path),
    }


def test_env_login_helper_loads_config_and_builds_login_ui(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from keepercommander.auth.login_steps import LoginUi
    from keepercommander.config_storage import loader

    config_path = tmp_path / "keeper.json"
    config_path.write_text(json.dumps({"server": "keepersecurity.eu"}), encoding="utf-8")
    loaded_config_paths: list[str] = []

    def fake_load_config_properties(params: Any) -> None:
        loaded_config_paths.append(params.config_filename)
        params.user = "stale-config-user@example.com"
        params.password = "stale-config-password"
        params.server = "keepersecurity.eu"

    def fake_login(params: Any, *, login_ui: Any) -> None:
        assert params.user == "operator@example.com"
        assert params.password == "secret"
        assert params.server == "keepersecurity.eu"
        assert isinstance(login_ui, LoginUi)
        params.session_token = "SESSION"

    monkeypatch.setattr(loader, "load_config_properties", fake_load_config_properties)
    monkeypatch.setattr("keepercommander.api.login", fake_login)
    monkeypatch.setattr(EnvLoginHelper, "_sleep_past_totp_edge", lambda *_args: None)

    params = EnvLoginHelper().keeper_login(
        "operator@example.com",
        "secret",
        "JBSWY3DPEHPK3PXP",
        config_path=str(config_path),
    )

    assert params.session_token == "SESSION"
    assert loaded_config_paths == [str(config_path)]


def test_env_login_helper_server_kwarg_overrides_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from keepercommander.config_storage import loader

    config_path = tmp_path / "keeper.json"
    config_path.write_text(json.dumps({"server": "keepersecurity.eu"}), encoding="utf-8")

    def fake_load_config_properties(params: Any) -> None:
        params.server = "keepersecurity.eu"

    def fake_login(params: Any, *, login_ui: Any) -> None:
        assert params.user == "operator@example.com"
        assert params.password == "secret"
        assert params.server == "keepersecurity.com"
        params.session_token = "SESSION"

    monkeypatch.setattr(loader, "load_config_properties", fake_load_config_properties)
    monkeypatch.setattr("keepercommander.api.login", fake_login)
    monkeypatch.setattr(EnvLoginHelper, "_sleep_past_totp_edge", lambda *_args: None)

    params = EnvLoginHelper().keeper_login(
        "operator@example.com",
        "secret",
        "JBSWY3DPEHPK3PXP",
        config_path=str(config_path),
        server="keepersecurity.com",
    )

    assert params.session_token == "SESSION"


def test_env_login_helper_invalid_config_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "keeper.json"
    config_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(CapabilityError) as exc_info:
        EnvLoginHelper().keeper_login(
            "operator@example.com",
            "secret",
            "JBSWY3DPEHPK3PXP",
            config_path=str(config_path),
        )

    assert "cannot parse KEEPER_CONFIG" in exc_info.value.reason


def test_auto_login_ui_answers_commander_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    from keepercommander.auth.login_steps import (
        DeviceApprovalChannel,
        LoginUi,
        TwoFactorDuration,
    )

    monkeypatch.setattr("keeper_sdk.auth.helper.time.time", lambda: 1)
    ui = _AutoLoginUi(
        password="secret",
        totp_secret="JBSWY3DPEHPK3PXP",
        login_ui_base=LoginUi,
        device_approval_channel=DeviceApprovalChannel.TwoFactor,
        two_factor_duration=TwoFactorDuration.Forever,
    )
    assert isinstance(ui, LoginUi)

    password_step = _PasswordStep()
    ui.on_password(password_step)
    assert password_step.verified_password == "secret"

    two_factor_step = _TwoFactorStep()
    ui.on_two_factor(two_factor_step)
    assert two_factor_step.duration == TwoFactorDuration.Forever
    assert two_factor_step.sent_codes[0][0] == "totp-channel"
    assert len(two_factor_step.sent_codes[0][1]) == 6

    device_step = _DeviceApprovalStep()
    ui.on_device_approval(device_step)
    assert device_step.sent_codes[0][0] == DeviceApprovalChannel.TwoFactor
    assert len(device_step.sent_codes[0][1]) == 6

    sso_step = _SsoStep()
    ui.on_sso_redirect(sso_step)
    ui.on_sso_data_key(sso_step)
    assert sso_step.used_password is True
    assert sso_step.cancelled is True


class _PasswordStep:
    def __init__(self) -> None:
        self.verified_password: str | None = None

    def verify_password(self, password: str) -> None:
        self.verified_password = password


class _TwoFactorChannel:
    channel_uid = "totp-channel"


class _TwoFactorStep:
    def __init__(self) -> None:
        self.duration: Any = None
        self.sent_codes: list[tuple[Any, str]] = []

    def get_channels(self) -> list[_TwoFactorChannel]:
        return [_TwoFactorChannel()]

    def send_code(self, channel_uid: Any, code: str) -> None:
        self.sent_codes.append((channel_uid, code))


class _DeviceApprovalStep:
    def __init__(self) -> None:
        self.sent_codes: list[tuple[Any, str]] = []

    def send_code(self, channel: Any, code: str) -> None:
        self.sent_codes.append((channel, code))


class _SsoStep:
    def __init__(self) -> None:
        self.used_password = False
        self.cancelled = False

    def login_with_password(self) -> None:
        self.used_password = True

    def cancel(self) -> None:
        self.cancelled = True
