"""CommanderCliProvider MSP managed-company apply tests."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.planner import Plan
from keeper_sdk.providers import commander_cli
from keeper_sdk.providers.commander_cli import CommanderCliProvider


def _mc(
    name: str,
    *,
    plan: str = "business",
    seats: int = 5,
    file_plan: str | None = None,
    addons: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"name": name, "plan": plan, "seats": seats}
    if file_plan is not None:
        row["file_plan"] = file_plan
    if addons is not None:
        row["addons"] = addons
    return row


def _plan(*changes: Change, allow_delete: bool = True) -> Plan:
    plan = Plan(
        manifest_name="msp-apply-test",
        changes=list(changes),
        order=[change.uid_ref or "" for change in changes],
    )
    setattr(plan, "allow_delete", allow_delete)
    return plan


def _provider(
    monkeypatch: pytest.MonkeyPatch,
    live_rows: list[dict[str, Any]],
) -> tuple[CommanderCliProvider, object]:
    provider = CommanderCliProvider.__new__(CommanderCliProvider)
    params = object()
    monkeypatch.setattr(commander_cli, "_ensure_keepercommander_version_for_apply", lambda: None)
    monkeypatch.setattr(provider, "_get_keeper_params", lambda: params)
    monkeypatch.setattr(provider, "_with_keeper_session_refresh", lambda operation: operation())
    monkeypatch.setattr(provider, "discover_managed_companies", lambda: list(live_rows))
    return provider, params


def _install_msp_module(
    monkeypatch: pytest.MonkeyPatch,
    *,
    add_command: type[Any] | None = None,
    update_command: type[Any] | None = None,
    remove_command: type[Any] | None = None,
) -> None:
    keepercommander_module = types.ModuleType("keepercommander")
    commands_module = types.ModuleType("keepercommander.commands")
    msp_module = types.ModuleType("keepercommander.commands.msp")
    setattr(keepercommander_module, "__path__", [])
    setattr(commands_module, "__path__", [])
    setattr(keepercommander_module, "commands", commands_module)
    setattr(commands_module, "msp", msp_module)
    if add_command is not None:
        msp_module.MSPAddCommand = add_command
    if update_command is not None:
        msp_module.MSPUpdateCommand = update_command
    if remove_command is not None:
        msp_module.MSPRemoveCommand = remove_command
    monkeypatch.setitem(sys.modules, "keepercommander", keepercommander_module)
    monkeypatch.setitem(sys.modules, "keepercommander.commands", commands_module)
    monkeypatch.setitem(sys.modules, "keepercommander.commands.msp", msp_module)


def test_create_mc_calls_msp_add_command_and_returns_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, params = _provider(monkeypatch, [])
    calls: list[tuple[object, dict[str, Any]]] = []

    class FakeMSPAddCommand:
        def execute(self, params_arg: object, **kwargs: Any) -> int:
            calls.append((params_arg, kwargs))
            return 456

    _install_msp_module(monkeypatch, add_command=FakeMSPAddCommand)
    change = Change(
        kind=ChangeKind.CREATE,
        uid_ref="Acme",
        resource_type="managed_company",
        title="Acme",
        after=_mc(
            "Acme",
            seats=7,
            file_plan="enterprise",
            addons=[
                {"name": "connection_manager", "seats": 3},
                {"name": "remote_browser_isolation", "seats": 0},
            ],
        ),
    )

    outcomes = provider.apply_msp_plan(_plan(change))

    assert [outcome.action for outcome in outcomes] == ["create"]
    assert outcomes[0].keeper_uid == "456"
    assert outcomes[0].details["mc_enterprise_id"] == 456
    assert calls == [
        (
            params,
            {
                "name": "Acme",
                "plan": "business",
                "seats": 7,
                "file_plan": "enterprise",
                "addon": ["connection_manager:3", "remote_browser_isolation"],
            },
        )
    ]


def test_update_mc_calls_msp_update_command_and_returns_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, params = _provider(monkeypatch, [{"name": "Acme", "mc_enterprise_id": 123}])
    calls: list[tuple[object, dict[str, Any]]] = []

    class FakeMSPUpdateCommand:
        def execute(self, params_arg: object, **kwargs: Any) -> None:
            calls.append((params_arg, kwargs))

    _install_msp_module(monkeypatch, update_command=FakeMSPUpdateCommand)
    change = Change(
        kind=ChangeKind.UPDATE,
        uid_ref="Acme",
        resource_type="managed_company",
        title="Acme",
        keeper_uid="123",
        before=_mc(
            "Acme",
            seats=5,
            addons=[
                {"name": "connection_manager", "seats": 2},
                {"name": "old_addon", "seats": 0},
            ],
        ),
        after=_mc(
            "Acme",
            seats=9,
            file_plan="enterprise",
            addons=[
                {"name": "connection_manager", "seats": 3},
                {"name": "remote_browser_isolation", "seats": 0},
            ],
        ),
    )

    outcomes = provider.apply_msp_plan(_plan(change))

    assert [outcome.action for outcome in outcomes] == ["update"]
    assert outcomes[0].keeper_uid == "123"
    assert outcomes[0].details["mc_enterprise_id"] == "123"
    assert calls == [
        (
            params,
            {
                "mc": "123",
                "name": "Acme",
                "plan": "business",
                "seats": 9,
                "file_plan": "enterprise",
                "add_addon": ["connection_manager:3", "remote_browser_isolation"],
                "remove_addon": ["old_addon"],
            },
        )
    ]


def test_delete_mc_calls_msp_remove_command_and_returns_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, params = _provider(monkeypatch, [{"name": "Old", "mc_enterprise_id": 123}])
    calls: list[tuple[object, dict[str, Any]]] = []

    class FakeMSPRemoveCommand:
        def execute(self, params_arg: object, **kwargs: Any) -> None:
            calls.append((params_arg, kwargs))

    _install_msp_module(monkeypatch, remove_command=FakeMSPRemoveCommand)
    change = Change(
        kind=ChangeKind.DELETE,
        uid_ref="Old",
        resource_type="managed_company",
        title="Old",
        keeper_uid="123",
        before=_mc("Old"),
    )

    outcomes = provider.apply_msp_plan(_plan(change, allow_delete=True))

    assert [outcome.action for outcome in outcomes] == ["delete"]
    assert outcomes[0].keeper_uid == "123"
    assert outcomes[0].details["mc_enterprise_id"] == "123"
    assert calls == [(params, {"mc": "123", "force": True})]


def test_empty_plan_raises_capability_error(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _params = _provider(monkeypatch, [])

    with pytest.raises(CapabilityError, match="MSP managed-company apply is not implemented"):
        provider.apply_msp_plan(Plan("msp-apply-test", [], []))


def test_partial_failure_raises_after_first_success(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, params = _provider(monkeypatch, [])
    calls: list[tuple[object, dict[str, Any]]] = []

    class CommandError(Exception):
        pass

    class FakeMSPAddCommand:
        def execute(self, params_arg: object, **kwargs: Any) -> int:
            calls.append((params_arg, kwargs))
            if kwargs["name"] == "Second":
                raise CommandError("boom")
            return 101

    _install_msp_module(monkeypatch, add_command=FakeMSPAddCommand)
    first = Change(
        kind=ChangeKind.CREATE,
        uid_ref="First",
        resource_type="managed_company",
        title="First",
        after=_mc("First", seats=2),
    )
    second = Change(
        kind=ChangeKind.CREATE,
        uid_ref="Second",
        resource_type="managed_company",
        title="Second",
        after=_mc("Second", seats=3),
    )

    with pytest.raises(CapabilityError) as exc_info:
        provider.apply_msp_plan(_plan(first, second))

    assert exc_info.value.uid_ref == "Second"
    assert exc_info.value.resource_type == "managed_company"
    assert "MSP managed-company create failed: CommandError: boom" in exc_info.value.reason
    assert calls == [
        (params, {"name": "First", "plan": "business", "seats": 2}),
        (params, {"name": "Second", "plan": "business", "seats": 3}),
    ]
