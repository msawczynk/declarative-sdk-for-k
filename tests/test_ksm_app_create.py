from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

import pytest

from keeper_sdk.secrets import bootstrap_ksm_application
from tests._fakes.commander import (
    FakeCommanderApi,
    FakeKeeperParams,
    FakeKsmCommand,
    FakeRecordAddCommand,
)
from tests._fakes.ksm import FakeRecord, install_fake_ksm_core

bootstrap_module = importlib.import_module("keeper_sdk.secrets.bootstrap")

ADMIN_UID = "ADM123456789"
TOKEN = "US:unit-bootstrap-token-redaction-check"


def _admin_fields() -> list[dict[str, object]]:
    return [
        {"type": "login", "label": "", "value": ["operator@example.invalid"]},
        {"type": "password", "label": "", "value": ["password-value"]},
        {
            "type": "oneTimeCode",
            "label": "",
            "value": ["otpauth://totp/SDK?secret=JBSWY3DPEHPK3PXP"],
        },
    ]


def _params_with_admin() -> FakeKeeperParams:
    params = FakeKeeperParams()
    params.add_record(uid=ADMIN_UID, title="Commander Admin", fields=_admin_fields())
    return params


@pytest.fixture(autouse=True)
def fake_commander(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeKsmCommand.reset()
    FakeRecordAddCommand.reset()
    monkeypatch.setattr(bootstrap_module, "KSMCommand", FakeKsmCommand)
    monkeypatch.setattr(bootstrap_module, "RecordAddCommand", FakeRecordAddCommand)
    monkeypatch.setattr(bootstrap_module, "commander_api", FakeCommanderApi)


def _install_admin_ksm(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_ksm_core(
        monkeypatch,
        {ADMIN_UID: FakeRecord(uid=ADMIN_UID, title="Commander Admin", fields=_admin_fields())},
    )


class SequencedKsmCommand(FakeKsmCommand):
    order: list[str] = []

    @classmethod
    def reset(cls) -> None:
        super().reset()
        cls.order = []

    @classmethod
    def add_new_v5_app(
        cls,
        params: FakeKeeperParams,
        app_name: str,
        force_to_add: bool = False,
        format_type: str = "table",
    ) -> str | None:
        cls.order.append("create_app")
        return super().add_new_v5_app(params, app_name, force_to_add, format_type)

    @classmethod
    def add_app_share(
        cls,
        params: FakeKeeperParams,
        secret_uids: list[str],
        app_name_or_uid: str,
        is_editable: bool,
    ) -> bool:
        cls.order.append("share_folder")
        return super().add_app_share(params, secret_uids, app_name_or_uid, is_editable)

    @classmethod
    def add_client(
        cls,
        params: FakeKeeperParams,
        app_name_or_uid: str,
        count: int,
        unlock_ip: bool,
        first_access_expire_on: int,
        access_expire_in_min: int | None,
        client_name: str | None = None,
        config_init: str | None = None,
        silent: bool = False,
        client_type: int = 1,
    ) -> list[dict[str, str]]:
        cls.order.append("one_time_token")
        return super().add_client(
            params,
            app_name_or_uid,
            count,
            unlock_ip,
            first_access_expire_on,
            access_expire_in_min,
            client_name,
            config_init,
            silent,
            client_type,
        )


class TokenKsmCommand(FakeKsmCommand):
    @classmethod
    def add_client(
        cls,
        params: FakeKeeperParams,
        app_name_or_uid: str,
        count: int,
        unlock_ip: bool,
        first_access_expire_on: int,
        access_expire_in_min: int | None,
        client_name: str | None = None,
        config_init: str | None = None,
        silent: bool = False,
        client_type: int = 1,
    ) -> list[dict[str, str]]:
        if not cls.get_app_record(params, app_name_or_uid):
            raise ValueError("fake app not found")
        cls.add_client_calls.append(
            {
                "app_name_or_uid": app_name_or_uid,
                "count": count,
                "unlock_ip": unlock_ip,
                "first_access_expire_on": first_access_expire_on,
                "access_expire_in_min": access_expire_in_min,
                "client_name": client_name,
                "config_init": config_init,
                "silent": silent,
                "client_type": client_type,
            }
        )
        return [{"oneTimeToken": TOKEN, "deviceToken": "fake-device"}]


def test_bootstrap_ksm_app_create_sequence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    params = _params_with_admin()
    _install_admin_ksm(monkeypatch)
    SequencedKsmCommand.reset()
    monkeypatch.setattr(bootstrap_module, "KSMCommand", SequencedKsmCommand)
    real_redeem = bootstrap_module._redeem_one_time_token

    def redeem_and_record(
        *,
        token: str,
        config_path: Path,
        overwrite: bool,
        partial: dict[str, Any],
    ) -> None:
        SequencedKsmCommand.order.append("redeem")
        real_redeem(token=token, config_path=config_path, overwrite=overwrite, partial=partial)

    monkeypatch.setattr(bootstrap_module, "_redeem_one_time_token", redeem_and_record)

    result = bootstrap_ksm_application(
        params=params,
        app_name="dsk-service-admin",
        admin_record_uid=ADMIN_UID,
        config_out=tmp_path / "ksm-config.json",
    )

    assert result.app_uid == "APP000000001"
    assert result.client_token_redeemed is True
    assert SequencedKsmCommand.order == [
        "create_app",
        "share_folder",
        "one_time_token",
        "redeem",
    ]


def test_bootstrap_idempotent_returns_existing_app_uid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    params = _params_with_admin()
    params.add_app(uid="APPEXISTING1", title="dsk-service-admin")
    _install_admin_ksm(monkeypatch)

    result = bootstrap_ksm_application(
        params=params,
        app_name="dsk-service-admin",
        admin_record_uid=ADMIN_UID,
        config_out=tmp_path / "existing-config.json",
    )

    assert result.app_uid == "APPEXISTING1"
    assert FakeKsmCommand.add_app_calls == []
    assert FakeKsmCommand.share_calls[0]["app_name_or_uid"] == "APPEXISTING1"


def test_bootstrap_redacts_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    params = _params_with_admin()
    _install_admin_ksm(monkeypatch)
    TokenKsmCommand.reset()
    monkeypatch.setattr(bootstrap_module, "KSMCommand", TokenKsmCommand)
    caplog.set_level(logging.DEBUG)

    result = bootstrap_ksm_application(
        params=params,
        app_name="dsk-service-admin",
        admin_record_uid=ADMIN_UID,
        config_out=tmp_path / "redacted-config.json",
    )
    captured = capsys.readouterr()

    assert result.client_token_redeemed is True
    assert TOKEN not in caplog.text
    assert TOKEN not in captured.out
    assert TOKEN not in captured.err
