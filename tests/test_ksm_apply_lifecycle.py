"""keeper-ksm.v1 CLI apply lifecycle coverage."""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any

import yaml
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY, EXIT_CHANGES, EXIT_OK
from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.planner import Plan
from keeper_sdk.providers import KsmMockProvider, commander_cli
from keeper_sdk.providers.commander_cli import CommanderCliProvider
from tests._fakes.commander import FakeKeeperParams, FakeKsmCommand

cli_main_module = importlib.import_module("keeper_sdk.cli.main")

MANIFEST_NAME = "ksm"


def _run(args: list[str]):
    return CliRunner().invoke(main, args, catch_exceptions=False)


def _app_doc() -> dict[str, Any]:
    return {
        "schema": "keeper-ksm.v1",
        "apps": [{"uid_ref": "app.api", "name": "API Service"}],
    }


def _write_manifest(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "ksm.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _install_fake_ksm_module(monkeypatch, command: type[Any]) -> None:
    keepercommander_module = types.ModuleType("keepercommander")
    api_module = types.ModuleType("keepercommander.api")
    commands_module = types.ModuleType("keepercommander.commands")
    ksm_module = types.ModuleType("keepercommander.commands.ksm")
    setattr(keepercommander_module, "__path__", [])
    setattr(commands_module, "__path__", [])
    api_module.sync_down = lambda params: None
    setattr(keepercommander_module, "api", api_module)
    setattr(keepercommander_module, "commands", commands_module)
    setattr(commands_module, "ksm", ksm_module)
    ksm_module.KSMCommand = command
    monkeypatch.setitem(sys.modules, "keepercommander", keepercommander_module)
    monkeypatch.setitem(sys.modules, "keepercommander.api", api_module)
    monkeypatch.setitem(sys.modules, "keepercommander.commands", commands_module)
    monkeypatch.setitem(sys.modules, "keepercommander.commands.ksm", ksm_module)


def test_ksm_app_create_plans_then_apply_mock_rc_zero(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = _write_manifest(tmp_path, _app_doc())
    provider = KsmMockProvider(MANIFEST_NAME)
    monkeypatch.setattr(cli_main_module, "KsmMockProvider", lambda manifest_name: provider)

    planned = _run(["--provider", "mock", "plan", str(path), "--json"])
    applied = _run(["--provider", "mock", "apply", str(path), "--auto-approve"])
    replanned = _run(["--provider", "mock", "plan", str(path), "--json"])

    assert planned.exit_code == EXIT_CHANGES, planned.output
    plan_payload = json.loads(planned.output)
    assert plan_payload["summary"]["create"] == 1
    assert plan_payload["changes"][0]["resource_type"] == "ksm_app"
    assert applied.exit_code == EXIT_OK, applied.output
    assert "marker_written=True" in applied.output
    assert provider.discover_ksm_apps()[0]["uid_ref"] == "app.api"
    assert replanned.exit_code == EXIT_OK, replanned.output
    assert json.loads(replanned.output)["summary"] == {
        "create": 0,
        "update": 0,
        "delete": 0,
        "conflict": 0,
        "noop": 1,
    }


def test_ksm_app_delete_requires_allow_delete_guard(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = _write_manifest(tmp_path, {"schema": "keeper-ksm.v1"})
    provider = KsmMockProvider(MANIFEST_NAME)
    provider.seed_ksm_state(_app_doc())
    monkeypatch.setattr(cli_main_module, "KsmMockProvider", lambda manifest_name: provider)

    guarded = _run(["--provider", "mock", "apply", str(path), "--auto-approve"])
    assert guarded.exit_code == EXIT_OK, guarded.output
    assert "nothing to do." in guarded.output
    assert provider.discover_ksm_apps()[0]["uid_ref"] == "app.api"

    deleted = _run(["--provider", "mock", "apply", str(path), "--allow-delete", "--auto-approve"])

    assert provider.discover_ksm_apps() == []
    assert deleted.exit_code == EXIT_OK, deleted.output
    assert "delete" in deleted.output


def test_commander_apply_ksm_plan_calls_add_new_v5_app(monkeypatch) -> None:
    provider = CommanderCliProvider.__new__(CommanderCliProvider)
    params = FakeKeeperParams()
    markers: list[tuple[str, dict[str, Any]]] = []
    FakeKsmCommand.reset()
    _install_fake_ksm_module(monkeypatch, FakeKsmCommand)
    monkeypatch.setattr(commander_cli, "_ensure_keepercommander_version_for_apply", lambda: None)
    monkeypatch.setattr(provider, "_get_keeper_params", lambda: params)
    monkeypatch.setattr(provider, "_with_keeper_session_refresh", lambda operation: operation())
    monkeypatch.setattr(provider, "_ksm_app_rows", lambda: [])
    monkeypatch.setattr(
        provider, "_write_marker", lambda uid, marker: markers.append((uid, marker))
    )
    provider._ksm_app_rows_cache = None
    change = Change(
        kind=ChangeKind.CREATE,
        uid_ref="app.api",
        resource_type="ksm_app",
        title="API Service",
        after={"uid_ref": "app.api", "name": "API Service", "scopes": [], "allowed_ips": []},
    )

    outcomes = provider.apply_ksm_plan(Plan(MANIFEST_NAME, [change], ["app.api"]))

    assert FakeKsmCommand.add_app_calls == ["API Service"]
    assert [outcome.action for outcome in outcomes] == ["create"]
    assert outcomes[0].keeper_uid == "APP000000001"
    assert markers[0][0] == "APP000000001"
    assert markers[0][1]["uid_ref"] == "app.api"
    assert markers[0][1]["resource_type"] == "ksm_app"


def test_ksm_apply_without_commander_support_exits_capability(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = _write_manifest(tmp_path, _app_doc())

    class MissingCommanderProvider:
        def discover_ksm_state(self) -> dict[str, list[dict[str, Any]]]:
            raise CapabilityError(
                reason="Commander KSM discovery unavailable",
                next_action="configure Commander before applying keeper-ksm.v1",
            )

    monkeypatch.setattr(
        cli_main_module, "_make_provider", lambda *args, **kwargs: MissingCommanderProvider()
    )
    result = _run(["--provider", "commander", "apply", str(path), "--auto-approve"])

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert "discovery failed: Commander KSM discovery unavailable" in result.output
