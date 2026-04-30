"""Commander in-process PAM gateway lifecycle helpers."""

from __future__ import annotations

import argparse
import sys
import types
from typing import Any

from keeper_sdk.providers.commander_cli import CommanderCliProvider
from tests._fakes.commander import FakeKeeperParams


class _FakeApi:
    @staticmethod
    def sync_down(params: FakeKeeperParams) -> None:
        params.sync_calls += 1


class _FakeGatewayCommand:
    calls: list[dict[str, Any]] = []

    @classmethod
    def reset(cls) -> None:
        cls.calls = []

    def execute(self, params: FakeKeeperParams, **kwargs: Any) -> str:
        self.__class__.calls.append({"params": params, "kwargs": kwargs})
        return "gateway-result"


class _FakeGatewayNew(_FakeGatewayCommand):
    def get_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="pam gateway new")
        parser.add_argument("--name", dest="gateway_name", required=True)
        parser.add_argument("--application", dest="ksm_app", required=True)
        parser.add_argument("--return_value", dest="return_value", action="store_true")
        return parser


class _FakeGatewayEdit(_FakeGatewayCommand):
    def get_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="pam gateway edit")
        parser.add_argument("--gateway", dest="gateway", required=True)
        parser.add_argument("--name", dest="gateway_name")
        parser.add_argument("--node-id", dest="node_id")
        return parser


class _FakeGatewayRemove(_FakeGatewayCommand):
    def get_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="pam gateway remove")
        parser.add_argument("--gateway", dest="gateway", required=True)
        return parser


def _install_fake_gateway_module(monkeypatch) -> None:
    keepercommander_module = types.ModuleType("keepercommander")
    api_module = types.ModuleType("keepercommander.api")
    commands_module = types.ModuleType("keepercommander.commands")
    discovery_module = types.ModuleType("keepercommander.commands.discoveryrotation")
    setattr(keepercommander_module, "__path__", [])
    setattr(commands_module, "__path__", [])
    api_module.sync_down = _FakeApi.sync_down
    discovery_module.PAMCreateGatewayCommand = _FakeGatewayNew
    discovery_module.PAMEditGatewayCommand = _FakeGatewayEdit
    discovery_module.PAMGatewayRemoveCommand = _FakeGatewayRemove
    monkeypatch.setitem(sys.modules, "keepercommander", keepercommander_module)
    monkeypatch.setitem(sys.modules, "keepercommander.api", api_module)
    monkeypatch.setitem(sys.modules, "keepercommander.commands", commands_module)
    monkeypatch.setitem(
        sys.modules,
        "keepercommander.commands.discoveryrotation",
        discovery_module,
    )


def _provider(params: FakeKeeperParams) -> CommanderCliProvider:
    provider = CommanderCliProvider.__new__(CommanderCliProvider)
    provider._keeper_params = params
    provider._keeper_login_attempted = False
    provider._with_keeper_session_refresh = lambda operation: operation()
    provider._get_keeper_params = lambda: params
    return provider


def test_pam_gateway_new_uses_commander_command_parser(monkeypatch) -> None:
    params = FakeKeeperParams()
    _install_fake_gateway_module(monkeypatch)
    _FakeGatewayNew.reset()
    provider = _provider(params)

    result = provider._pam_gateway_new("New Gateway", "Gateway App")

    assert result == "gateway-result"
    assert _FakeGatewayNew.calls[0]["kwargs"] == {
        "gateway_name": "New Gateway",
        "ksm_app": "Gateway App",
        "return_value": True,
    }
    assert params.sync_calls == 1


def test_pam_gateway_edit_and_remove_use_expected_argv_shape(monkeypatch) -> None:
    params = FakeKeeperParams()
    _install_fake_gateway_module(monkeypatch)
    _FakeGatewayEdit.reset()
    _FakeGatewayRemove.reset()
    provider = _provider(params)

    provider._pam_gateway_edit(gateway="GW_UID", name="Renamed Gateway", node_id="123")
    provider._pam_gateway_remove("GW_UID")

    assert _FakeGatewayEdit.calls[0]["kwargs"] == {
        "gateway": "GW_UID",
        "gateway_name": "Renamed Gateway",
        "node_id": "123",
    }
    assert _FakeGatewayRemove.calls[0]["kwargs"] == {"gateway": "GW_UID"}
