from __future__ import annotations

import builtins
import importlib
import json
from pathlib import Path
from typing import Any

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


def test_bootstrap_second_run_reuses_created_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    params = _params_with_admin()
    _install_admin_ksm(monkeypatch)

    first = bootstrap_ksm_application(
        params=params,
        app_name="dsk-service-admin",
        admin_record_uid=ADMIN_UID,
        config_out=tmp_path / "first-config.json",
    )
    second = bootstrap_ksm_application(
        params=params,
        app_name="dsk-service-admin",
        admin_record_uid=ADMIN_UID,
        config_out=tmp_path / "second-config.json",
    )

    assert second.app_uid == first.app_uid
    assert FakeKsmCommand.add_app_calls == ["dsk-service-admin"]
    assert [call["secret_uids"] for call in FakeKsmCommand.share_calls] == [
        [ADMIN_UID],
        [ADMIN_UID],
    ]


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


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"app_name": " "}, "app_name must be non-empty"),
        (
            {"admin_record_uid": ADMIN_UID, "create_admin_record": True},
            "requires exactly one",
        ),
        ({"admin_record_uid": None, "create_admin_record": False}, "requires exactly one"),
        ({"first_access_minutes": -1}, "must be non-negative"),
        ({"config_out": "missing/config.json"}, "config parent does not exist"),
    ],
)
def test_bootstrap_validate_input_edge_failures(
    tmp_path: Path,
    overrides: dict[str, object],
    expected: str,
) -> None:
    kwargs: dict[str, object] = {
        "app_name": "dsk-service-admin",
        "admin_record_uid": ADMIN_UID,
        "create_admin_record": False,
        "config_out": tmp_path / "config.json",
        "first_access_minutes": 10,
        "overwrite": False,
    }
    kwargs.update(overrides)
    if kwargs["config_out"] == "missing/config.json":
        kwargs["config_out"] = tmp_path / "missing" / "config.json"

    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_module._validate_inputs(**kwargs)

    assert expected in exc_info.value.reason


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


def test_bootstrap_missing_admin_record_fails_after_sync(tmp_path: Path) -> None:
    params = FakeKeeperParams()

    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_ksm_application(
            params=params,
            app_name="dsk-service-admin",
            admin_record_uid=ADMIN_UID,
            config_out=tmp_path / "missing-admin-config.json",
        )

    assert "not found" in exc_info.value.reason
    assert params.sync_calls == 1


def test_resolve_admin_record_requires_resolution_mode() -> None:
    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_module._resolve_admin_record(
            params=FakeKeeperParams(),
            app_name="dsk-service-admin",
            admin_record_uid=None,
            create_admin_record=False,
            partial={"app_uid": None},
        )

    assert "cannot resolve" in exc_info.value.reason


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


def test_create_or_reuse_app_falls_back_to_sync_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    params = FakeKeeperParams()

    def add_app_without_uid(
        cls: type[FakeKsmCommand],
        params: FakeKeeperParams,
        app_name: str,
        force_to_add: bool = False,
        format_type: str = "table",
    ) -> str:
        _ = force_to_add, format_type
        cls.add_app_calls.append(app_name)
        params.add_app(uid="APPFALLBACK1", title=app_name)
        return ""

    monkeypatch.setattr(FakeKsmCommand, "add_new_v5_app", classmethod(add_app_without_uid))

    app_uid = bootstrap_module._create_or_reuse_app(
        params=params,
        app_name="dsk-service-admin",
        partial={"app_uid": None},
    )

    assert app_uid == "APPFALLBACK1"


def test_create_or_reuse_app_errors_when_create_result_has_no_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def add_app_without_record(
        cls: type[FakeKsmCommand],
        params: FakeKeeperParams,
        app_name: str,
        force_to_add: bool = False,
        format_type: str = "table",
    ) -> str:
        _ = cls, params, app_name, force_to_add, format_type
        return ""

    monkeypatch.setattr(FakeKsmCommand, "add_new_v5_app", classmethod(add_app_without_record))

    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_module._create_or_reuse_app(
            params=FakeKeeperParams(),
            app_name="dsk-service-admin",
            partial={"app_uid": None},
        )

    assert "was not created" in exc_info.value.reason


def test_create_or_reuse_app_wraps_commander_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_add_app(
        cls: type[FakeKsmCommand],
        params: FakeKeeperParams,
        app_name: str,
        force_to_add: bool = False,
        format_type: str = "table",
    ) -> str:
        _ = cls, params, app_name, force_to_add, format_type
        raise RuntimeError("app denied")

    monkeypatch.setattr(FakeKsmCommand, "add_new_v5_app", classmethod(fail_add_app))

    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_module._create_or_reuse_app(
            params=FakeKeeperParams(),
            app_name="dsk-service-admin",
            partial={"app_uid": None},
        )

    assert "creating KSM application failed: RuntimeError: app denied" in exc_info.value.reason


def test_share_record_with_app_wraps_commander_failure() -> None:
    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_module._share_record_with_app(
            params=FakeKeeperParams(),
            app_uid="APP404",
            record_uid=ADMIN_UID,
            editable=False,
            partial={"app_uid": "APP404", "record_uid": ADMIN_UID},
        )

    assert "sharing record into KSM application failed" in exc_info.value.reason


def test_generate_one_time_token_wraps_commander_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_add_client(
        cls: type[FakeKsmCommand],
        params: FakeKeeperParams,
        app_name_or_uid: str,
        count: int,
        unlock_ip: bool,
        first_access_expire_on: int,
        access_expire_in_min: int | None,
        **kwargs: Any,
    ) -> list[dict[str, str]]:
        _ = (
            cls,
            params,
            app_name_or_uid,
            count,
            unlock_ip,
            first_access_expire_on,
            access_expire_in_min,
            kwargs,
        )
        raise RuntimeError("client denied")

    monkeypatch.setattr(FakeKsmCommand, "add_client", classmethod(fail_add_client))

    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_module._generate_one_time_token(
            params=FakeKeeperParams(),
            app_uid="APP123",
            first_access_minutes=10,
            unlock_ip=False,
            partial={"app_uid": "APP123"},
        )

    assert "creating KSM client token failed: RuntimeError: client denied" in exc_info.value.reason


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        (None, "did not return"),
        ({}, "did not return"),
        ([{}], "without a one-time token"),
        ([{"oneTimeToken": ""}], "without a one-time token"),
    ],
)
def test_generate_one_time_token_rejects_unexpected_response_shapes(
    monkeypatch: pytest.MonkeyPatch,
    tokens: object,
    expected: str,
) -> None:
    def add_client_response(
        cls: type[FakeKsmCommand],
        params: FakeKeeperParams,
        app_name_or_uid: str,
        count: int,
        unlock_ip: bool,
        first_access_expire_on: int,
        access_expire_in_min: int | None,
        **kwargs: Any,
    ) -> object:
        _ = (
            cls,
            params,
            app_name_or_uid,
            count,
            unlock_ip,
            first_access_expire_on,
            access_expire_in_min,
            kwargs,
        )
        return tokens

    monkeypatch.setattr(FakeKsmCommand, "add_client", classmethod(add_client_response))

    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_module._generate_one_time_token(
            params=FakeKeeperParams(),
            app_uid="APP123",
            first_access_minutes=10,
            unlock_ip=False,
            partial={"app_uid": "APP123"},
        )

    assert expected in exc_info.value.reason


def test_redeem_one_time_token_requires_ksm_core(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original_import = builtins.__import__

    def fail_ksm_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name.startswith("keeper_secrets_manager_core"):
            raise ImportError("missing ksm core")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fail_ksm_import)

    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_module._redeem_one_time_token(
            token="US:fake-bootstrap-token",
            config_path=tmp_path / "config.json",
            overwrite=False,
            partial={"app_uid": "APP123"},
        )

    assert "keeper_secrets_manager_core is required" in exc_info.value.reason


def test_redeem_one_time_token_overwrite_unlinks_then_wraps_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("old", encoding="utf-8")
    fake_ksm = install_fake_ksm_core(monkeypatch, {})

    def fail_init(
        self: object, *, config: object, token: str | None = None, **kwargs: object
    ) -> None:
        _ = self, config, token, kwargs
        raise RuntimeError("token consumed")

    monkeypatch.setattr(fake_ksm, "__init__", fail_init)

    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_module._redeem_one_time_token(
            token="US:fake-bootstrap-token",
            config_path=config_path,
            overwrite=True,
            partial={"app_uid": "APP123"},
        )

    assert (
        "redeeming KSM client token failed: RuntimeError: token consumed" in exc_info.value.reason
    )
    assert not config_path.exists()


def test_verify_redeemed_config_wraps_unexpected_store_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class ExplodingStore:
        def __init__(self, *, config_path: Path) -> None:
            self.config_path = config_path

        def describe(self, uid: str) -> dict[str, object]:
            _ = uid
            raise RuntimeError("fetch exploded")

    monkeypatch.setattr(bootstrap_module, "KsmSecretStore", ExplodingStore)
    monkeypatch.setenv("KEEPER_SDK_KSM_BOOTSTRAP_VERIFY_TIMEOUT", "0")

    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_module._verify_redeemed_config(
            config_path=tmp_path / "config.json",
            admin_record_uid=ADMIN_UID,
            partial={"app_uid": "APP123", "record_uid": ADMIN_UID},
        )

    assert "KSM config verification failed after 0s: RuntimeError: fetch exploded" in (
        exc_info.value.reason
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("not-a-number", 20.0),
        ("-1", 0.0),
        ("301", 300.0),
    ],
)
def test_verify_budget_seconds_falls_back_and_clamps(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
    expected: float,
) -> None:
    monkeypatch.setenv("KEEPER_SDK_KSM_BOOTSTRAP_VERIFY_TIMEOUT", raw)

    assert bootstrap_module._verify_budget_seconds() == expected


def test_create_record_wraps_commander_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_execute(self: FakeRecordAddCommand, params: FakeKeeperParams, **kwargs: object) -> str:
        _ = self, params, kwargs
        raise RuntimeError("record denied")

    monkeypatch.setattr(FakeRecordAddCommand, "execute", fail_execute)

    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_module._create_record(
            params=FakeKeeperParams(),
            record_data={"type": "login", "title": "Broken", "fields": [], "custom": []},
            partial={"record_uid": None},
        )

    assert (
        "creating Keeper vault record failed: RuntimeError: record denied" in exc_info.value.reason
    )


def test_create_record_rejects_empty_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_uid(self: FakeRecordAddCommand, params: FakeKeeperParams, **kwargs: object) -> str:
        _ = self, params, kwargs
        return ""

    monkeypatch.setattr(FakeRecordAddCommand, "execute", no_uid)

    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_module._create_record(
            params=FakeKeeperParams(),
            record_data={"type": "login", "title": "No UID", "fields": [], "custom": []},
            partial={"record_uid": None},
        )

    assert "did not return a UID" in exc_info.value.reason


def test_sync_down_wraps_commander_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenCommanderApi:
        @staticmethod
        def sync_down(params: FakeKeeperParams) -> None:
            _ = params
            raise RuntimeError("sync denied")

    monkeypatch.setattr(bootstrap_module, "commander_api", BrokenCommanderApi)

    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_module._sync_down(params=FakeKeeperParams(), partial={"app_uid": None})

    assert "Commander sync_down failed: RuntimeError: sync denied" in exc_info.value.reason


def test_record_cache_entry_finds_nested_record_uid_and_returns_none() -> None:
    params = FakeKeeperParams()
    nested = {"record_uid": ADMIN_UID}
    params.record_cache["cache-key"] = nested

    assert bootstrap_module._record_cache_entry(params, ADMIN_UID) is nested
    assert bootstrap_module._record_cache_entry(params, "MISSING123") is None


def test_record_data_invalid_json_returns_empty_dict() -> None:
    assert bootstrap_module._record_data({"data_unencrypted": b"{not-json"}) == {}


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (None, ""),
        (b'{"app_uid":"APPBYTES1"}', "APPBYTES1"),
        ("not-json", ""),
        (["APP"], ""),
    ],
)
def test_app_uid_from_create_result_shapes(result: object, expected: str) -> None:
    assert bootstrap_module._app_uid_from_create_result(result) == expected


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


def test_bootstrap_verify_retries_until_share_propagates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The verify loop should ride out a short share-propagation delay.

    Simulates the live tenant's ``add_app_share`` → ``add_client`` →
    ``SecretsManager(token=...)`` race: the first two ``get_secrets``
    calls return an empty list (share not yet propagated), the third
    returns the populated record. Bootstrap must succeed without
    increasing the budget, and we should observe more than one verify
    attempt via ``init_calls`` / ``get_secrets_calls``.
    """
    params = _params_with_admin()
    fake_ksm = install_fake_ksm_core(
        monkeypatch,
        {ADMIN_UID: FakeRecord(uid=ADMIN_UID, title="Commander Admin", fields=_admin_fields())},
        visibility_delay=2,
    )
    monkeypatch.setenv("KEEPER_SDK_KSM_BOOTSTRAP_VERIFY_TIMEOUT", "10")

    result = bootstrap_ksm_application(
        params=params,
        app_name="dsk-service-admin",
        admin_record_uid=ADMIN_UID,
        config_out=tmp_path / "retry-config.json",
    )

    assert result.client_token_redeemed is True
    assert fake_ksm.get_secrets_calls >= 3
    assert len(fake_ksm.init_calls) >= 3


def test_bootstrap_verify_gives_up_when_share_never_propagates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """If propagation never lands within the budget, surface a clear error.

    The retry loop is bounded; the failure mode must mention the env var
    that operators can raise so the next-action is mechanical.
    """
    params = _params_with_admin()
    install_fake_ksm_core(
        monkeypatch,
        {ADMIN_UID: FakeRecord(uid=ADMIN_UID, title="Commander Admin", fields=_admin_fields())},
        visibility_delay=10_000,
    )
    monkeypatch.setenv("KEEPER_SDK_KSM_BOOTSTRAP_VERIFY_TIMEOUT", "0")

    with pytest.raises(CapabilityError) as exc_info:
        bootstrap_ksm_application(
            params=params,
            app_name="dsk-service-admin",
            admin_record_uid=ADMIN_UID,
            config_out=tmp_path / "give-up-config.json",
        )

    assert "verification failed" in exc_info.value.reason
    assert "KEEPER_SDK_KSM_BOOTSTRAP_VERIFY_TIMEOUT" in (exc_info.value.next_action or "")
