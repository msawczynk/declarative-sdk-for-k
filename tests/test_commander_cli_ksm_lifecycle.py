"""Commander in-process KSM app delete and share-update helpers."""

from __future__ import annotations

import sys
import types
from typing import Any

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.planner import Plan
from keeper_sdk.providers import commander_cli
from keeper_sdk.providers.commander_cli import CommanderCliProvider
from tests._fakes.commander import FakeKeeperParams, FakeKsmCommand


class _LifecycleKsmCommand(FakeKsmCommand):
    remove_calls: list[dict[str, Any]] = []
    update_share_calls: list[dict[str, Any]] = []

    @classmethod
    def reset(cls) -> None:
        super().reset()
        cls.remove_calls = []
        cls.update_share_calls = []

    @classmethod
    def remove_v5_app(
        cls,
        params: FakeKeeperParams,
        app_name_or_uid: str,
        purge: bool,
        force: bool,
    ) -> None:
        cls.remove_calls.append(
            {
                "app_name_or_uid": app_name_or_uid,
                "purge": purge,
                "force": force,
            }
        )

    @classmethod
    def update_app_share(
        cls,
        params: FakeKeeperParams,
        secret_uids: list[str],
        app_name_or_uid: str,
        is_editable: bool,
    ) -> None:
        cls.update_share_calls.append(
            {
                "secret_uids": list(secret_uids),
                "app_name_or_uid": app_name_or_uid,
                "is_editable": is_editable,
            }
        )


def _install_fake_ksm_module(monkeypatch, command: type[Any]) -> None:
    keepercommander_module = types.ModuleType("keepercommander")
    api_module = types.ModuleType("keepercommander.api")
    commands_module = types.ModuleType("keepercommander.commands")
    ksm_module = types.ModuleType("keepercommander.commands.ksm")
    setattr(keepercommander_module, "__path__", [])
    setattr(commands_module, "__path__", [])
    api_module.sync_down = lambda params: setattr(params, "sync_calls", params.sync_calls + 1)
    setattr(keepercommander_module, "api", api_module)
    setattr(keepercommander_module, "commands", commands_module)
    setattr(commands_module, "ksm", ksm_module)
    ksm_module.KSMCommand = command
    monkeypatch.setitem(sys.modules, "keepercommander", keepercommander_module)
    monkeypatch.setitem(sys.modules, "keepercommander.api", api_module)
    monkeypatch.setitem(sys.modules, "keepercommander.commands", commands_module)
    monkeypatch.setitem(sys.modules, "keepercommander.commands.ksm", ksm_module)


def _provider(params: FakeKeeperParams) -> CommanderCliProvider:
    provider = CommanderCliProvider.__new__(CommanderCliProvider)
    provider._keeper_params = params
    provider._keeper_login_attempted = False
    provider._ksm_app_rows_cache = None
    provider._with_keeper_session_refresh = lambda operation: operation()
    provider._get_keeper_params = lambda: params
    return provider


def test_ksm_app_remove_calls_commander_remove_v5_app(monkeypatch) -> None:
    params = FakeKeeperParams()
    _LifecycleKsmCommand.reset()
    _install_fake_ksm_module(monkeypatch, _LifecycleKsmCommand)
    provider = _provider(params)

    provider.ksm_app_remove("APP_UID", purge=True, force=True)

    assert _LifecycleKsmCommand.remove_calls == [
        {"app_name_or_uid": "APP_UID", "purge": True, "force": True}
    ]
    assert params.sync_calls == 1


def test_ksm_app_share_update_calls_commander_update_app_share(monkeypatch) -> None:
    params = FakeKeeperParams()
    _LifecycleKsmCommand.reset()
    _install_fake_ksm_module(monkeypatch, _LifecycleKsmCommand)
    provider = _provider(params)

    provider.ksm_app_share_update("APP_UID", ["REC_UID"], editable=True)

    assert _LifecycleKsmCommand.update_share_calls == [
        {
            "secret_uids": ["REC_UID"],
            "app_name_or_uid": "APP_UID",
            "is_editable": True,
        }
    ]
    assert params.sync_calls == 2


def test_apply_ksm_plan_deletes_app_and_updates_share(monkeypatch) -> None:
    params = FakeKeeperParams()
    _LifecycleKsmCommand.reset()
    _install_fake_ksm_module(monkeypatch, _LifecycleKsmCommand)
    monkeypatch.setattr(commander_cli, "_ensure_keepercommander_version_for_apply", lambda: None)
    provider = _provider(params)
    changes = [
        Change(
            kind=ChangeKind.UPDATE,
            uid_ref="share:keeper-ksm:apps:app.api:keeper-vault:records:rec.db",
            resource_type="ksm_record_share",
            title="app -> rec",
            keeper_uid="APP_UID|REC_UID",
            before={"editable": False},
            after={"editable": True},
        ),
        Change(
            kind=ChangeKind.DELETE,
            uid_ref="app.api",
            resource_type="ksm_app",
            title="API Service",
            keeper_uid="APP_UID",
            before={"uid_ref": "app.api", "name": "API Service"},
        ),
    ]

    outcomes = provider.apply_ksm_plan(Plan("ksm", changes, []))

    assert [outcome.action for outcome in outcomes] == ["update", "delete"]
    assert _LifecycleKsmCommand.update_share_calls[0]["secret_uids"] == ["REC_UID"]
    assert _LifecycleKsmCommand.update_share_calls[0]["is_editable"] is True
    assert _LifecycleKsmCommand.remove_calls[0]["app_name_or_uid"] == "APP_UID"
