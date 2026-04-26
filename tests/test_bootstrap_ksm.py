from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main as cli
from keeper_sdk.cli.main import EXIT_CAPABILITY
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.secrets import BootstrapResult, bootstrap_ksm_application
from tests._fakes.commander import (
    FakeCommanderApi,
    FakeKeeperParams,
    FakeKsmCommand,
    FakeRecordAddCommand,
)
from tests._fakes.ksm import FakeRecord, install_fake_ksm_core

bootstrap_module = importlib.import_module("keeper_sdk.secrets.bootstrap")
cli_main_module = importlib.import_module("keeper_sdk.cli.main")

ADMIN_UID = "ADM123456789"
BUS_UID = "BUS123456789"


def _admin_fields() -> list[dict[str, object]]:
    return [
        {"type": "login", "label": "", "value": ["operator@example.invalid"]},
        {"type": "password", "label": "", "value": ["password-value"]},
        {"type": "oneTimeCode", "label": "", "value": ["otpauth://totp/SDK?secret=JBSWY3DPEHPK3PXP"]},
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


def _install_admin_ksm(monkeypatch: pytest.MonkeyPatch, uid: str = ADMIN_UID) -> None:
    install_fake_ksm_core(
        monkeypatch,
        {uid: FakeRecord(uid=uid, title="Commander Admin", fields=_admin_fields())},
    )


def test_bootstrap_happy_path_existing_admin_redeems_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    params = _params_with_admin()
    _install_admin_ksm(monkeypatch)
    config_out = tmp_path / "ksm-config.json"

    result = bootstrap_ksm_application(
        params=params,
        app_name="dsk-service-admin",
        admin_record_uid=ADMIN_UID,
        config_out=config_out,
    )

    assert isinstance(result, BootstrapResult)
    assert result.app_uid == "APP000000001"
    assert result.admin_record_uid == ADMIN_UID
    assert result.config_path == str(config_out)
    assert result.client_token_redeemed is True
    assert config_out.is_file()
    assert FakeKsmCommand.share_calls[0] == {
        "secret_uids": [ADMIN_UID],
        "app_name_or_uid": "APP000000001",
        "is_editable": False,
    }
    assert FakeKsmCommand.add_client_calls[0]["silent"] is True


def test_bootstrap_create_admin_record_uses_placeholder_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    params = FakeKeeperParams()
    created_uid = "REC000000001"
    install_fake_ksm_core(
        monkeypatch,
        {created_uid: FakeRecord(uid=created_uid, title="Created Admin", fields=_admin_fields())},
    )

    result = bootstrap_ksm_application(
        params=params,
        app_name="dsk-service-admin",
        create_admin_record=True,
        config_out=tmp_path / "created-config.json",
    )

    assert result.admin_record_uid == created_uid
    assert result.created_admin_record is True
    created = FakeRecordAddCommand.calls[0]
    assert created["title"] == "dsk-service-admin admin login"
    assert created["fields"] == [
        {"type": "login", "value": [""]},
        {"type": "password", "value": [""]},
        {"type": "oneTimeCode", "value": [""]},
    ]


def test_bootstrap_with_bus_creates_directory_record(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    params = _params_with_admin()
    _install_admin_ksm(monkeypatch)

    result = bootstrap_ksm_application(
        params=params,
        app_name="dsk-service-admin",
        admin_record_uid=ADMIN_UID,
        config_out=tmp_path / "bus-config.json",
        create_bus_directory=True,
    )

    assert result.bus_directory_uid == "REC000000001"
    assert result.created_bus_directory is True
    assert FakeRecordAddCommand.calls[0]["custom"] == [
        {"type": "json", "label": "topics", "value": ["{}"]}
    ]
    assert FakeKsmCommand.share_calls[1]["secret_uids"] == ["REC000000001"]
    assert FakeKsmCommand.share_calls[1]["is_editable"] is True


def test_bootstrap_with_bus_reuses_existing_directory_record(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    params = _params_with_admin()
    params.add_record(
        uid=BUS_UID,
        title="dsk-agent-bus-directory",
        record_type="encryptedNotes",
        custom=[{"type": "json", "label": "topics", "value": ["{}"]}],
    )
    _install_admin_ksm(monkeypatch)

    result = bootstrap_ksm_application(
        params=params,
        app_name="dsk-service-admin",
        admin_record_uid=ADMIN_UID,
        config_out=tmp_path / "reuse-bus-config.json",
        create_bus_directory=True,
    )

    assert result.bus_directory_uid == BUS_UID
    assert result.created_bus_directory is False
    assert FakeRecordAddCommand.calls == []
    assert FakeKsmCommand.share_calls[1]["secret_uids"] == [BUS_UID]


def test_bootstrap_reuses_existing_app_by_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    params = _params_with_admin()
    params.add_app(uid="APPREUSE123", title="dsk-service-admin")
    _install_admin_ksm(monkeypatch)

    result = bootstrap_ksm_application(
        params=params,
        app_name="dsk-service-admin",
        admin_record_uid=ADMIN_UID,
        config_out=tmp_path / "reuse-app-config.json",
    )

    assert result.app_uid == "APPREUSE123"
    assert FakeKsmCommand.add_app_calls == []


def test_bootstrap_existing_config_without_overwrite_fails_before_commander(
    tmp_path: Path,
) -> None:
    params = _params_with_admin()
    config_out = tmp_path / "exists.json"
    config_out.write_text("{}", encoding="utf-8")

    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_ksm_application(
            params=params,
            app_name="dsk-service-admin",
            admin_record_uid=ADMIN_UID,
            config_out=config_out,
        )

    assert "--overwrite" in (exc_info.value.next_action or "")
    assert params.sync_calls == 0
    assert FakeKsmCommand.add_app_calls == []
    assert FakeRecordAddCommand.calls == []


@pytest.mark.parametrize("app_name", ["bad/name", "x" * 65])
def test_bootstrap_invalid_app_name_fails_before_commander(
    app_name: str,
    tmp_path: Path,
) -> None:
    params = _params_with_admin()

    with pytest.raises(CapabilityError):
        bootstrap_ksm_application(
            params=params,
            app_name=app_name,
            admin_record_uid=ADMIN_UID,
            config_out=tmp_path / "bad-config.json",
        )

    assert params.sync_calls == 0
    assert FakeKsmCommand.add_app_calls == []
    assert FakeRecordAddCommand.calls == []


def test_bootstrap_verification_failure_preserves_partial_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    params = _params_with_admin()
    install_fake_ksm_core(
        monkeypatch,
        {
            ADMIN_UID: FakeRecord(
                uid=ADMIN_UID,
                title="Commander Admin",
                fields=[{"type": "login", "label": "", "value": ["operator@example.invalid"]}],
            )
        },
    )

    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_ksm_application(
            params=params,
            app_name="dsk-service-admin",
            admin_record_uid=ADMIN_UID,
            config_out=tmp_path / "verify-fail-config.json",
        )

    assert "verification failed" in exc_info.value.reason
    assert exc_info.value.context["app_uid"] == "APP000000001"
    assert exc_info.value.context["record_uid"] == ADMIN_UID


def test_bootstrap_cli_success_outputs_single_json_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    params = _params_with_admin()
    _install_admin_ksm(monkeypatch)

    def noisy_params(login_helper: str) -> FakeKeeperParams:
        _ = login_helper
        print("login-helper noise")
        return params

    monkeypatch.setattr(cli_main_module, "_params_for_bootstrap", noisy_params)
    config_out = tmp_path / "cli-config.json"

    result = CliRunner().invoke(
        cli,
        [
            "bootstrap-ksm",
            "--app-name",
            "dsk-service-admin",
            "--admin-record-uid",
            ADMIN_UID,
            "--config-out",
            str(config_out),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["status"] == "ok"
    assert payload["app_uid"] == "APP000..."
    assert payload["record_uid"] == "ADM123..."
    assert payload["config_path"] == str(config_out.resolve())
    assert "fake-bootstrap-token" not in result.output
    assert "login-helper noise" not in result.output


def test_bootstrap_cli_capability_error_outputs_failure_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    params = _params_with_admin()
    monkeypatch.setattr(cli_main_module, "_params_for_bootstrap", lambda login_helper: params)
    config_out = tmp_path / "exists.json"
    config_out.write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "bootstrap-ksm",
            "--app-name",
            "dsk-service-admin",
            "--admin-record-uid",
            ADMIN_UID,
            "--config-out",
            str(config_out),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == EXIT_CAPABILITY
    payload = json.loads(result.output)
    assert payload["status"] == "fail"
    assert "--overwrite" in payload["next_action"]
