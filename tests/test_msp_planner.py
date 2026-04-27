"""Planner and CLI bundle wiring for msp-environment.v1 (P5)."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CHANGES
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.interfaces import ApplyOutcome
from keeper_sdk.core.planner import Plan
from keeper_sdk.providers import MockProvider
from keeper_sdk.providers.commander_cli import CommanderCliProvider

cli_main_module = importlib.import_module("keeper_sdk.cli.main")

MSP_UNSUPPORTED = "MSP family unsupported on commander provider; planned for P7"


def _run(args: list[str]):
    return CliRunner().invoke(main, args, catch_exceptions=False)


def _write_manifest(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "msp.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _single_mc_yaml(*, name: str = "Acme", seats: int = 5) -> str:
    return (
        "schema: msp-environment.v1\n"
        "name: msp-plan-test\n"
        "managed_companies:\n"
        f"  - name: {name}\n"
        "    plan: business\n"
        f"    seats: {seats}\n"
    )


class TrackingMspProvider(MockProvider):
    def __init__(self, manifest_name: str | None = None) -> None:
        super().__init__(manifest_name)
        self.apply_plan_calls = 0
        self.apply_msp_plan_calls = 0

    def apply_plan(self, plan: Plan, *, dry_run: bool = False) -> list[ApplyOutcome]:
        self.apply_plan_calls += 1
        raise AssertionError("MSP CLI dispatch must not call apply_plan")

    def apply_msp_plan(self, plan: Plan, *, dry_run: bool = False) -> list[ApplyOutcome]:
        self.apply_msp_plan_calls += 1
        return super().apply_msp_plan(plan, dry_run=dry_run)


def test_plan_msp_mock_builds_managed_company_plan(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _single_mc_yaml())

    result = _run(["plan", str(path), "--provider", "mock", "--json"])

    assert result.exit_code == EXIT_CHANGES, result.output
    plan = json.loads(result.output)
    assert plan["manifest_name"] == "msp-plan-test"
    assert plan["order"] == ["Acme"]
    assert plan["summary"] == {
        "create": 1,
        "update": 0,
        "delete": 0,
        "conflict": 0,
        "noop": 0,
    }
    assert plan["changes"][0]["kind"] == "create"
    assert plan["changes"][0]["resource_type"] == "managed_company"
    assert plan["changes"][0]["after"]["name"] == "Acme"


def test_apply_msp_mock_dispatches_to_apply_msp_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_manifest(tmp_path, _single_mc_yaml())
    provider = TrackingMspProvider("msp-plan-test")

    def provider_factory(manifest_name: str | None = None) -> TrackingMspProvider:
        return provider

    monkeypatch.setattr(cli_main_module, "MockProvider", provider_factory)

    result = _run(["apply", str(path), "--provider", "mock", "--yes"])

    assert result.exit_code == 0, result.output
    assert provider.apply_msp_plan_calls == 1
    assert provider.apply_plan_calls == 0
    assert provider.discover_managed_companies()[0]["name"] == "Acme"


def test_apply_then_plan_msp_mock_is_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_manifest(tmp_path, _single_mc_yaml())
    provider = MockProvider("msp-plan-test")

    def provider_factory(manifest_name: str | None = None) -> MockProvider:
        return provider

    monkeypatch.setattr(cli_main_module, "MockProvider", provider_factory)

    apply_result = _run(["apply", str(path), "--provider", "mock", "--yes"])
    assert apply_result.exit_code == 0, apply_result.output

    plan_result = _run(["plan", str(path), "--provider", "mock", "--json"])
    assert plan_result.exit_code == 0, plan_result.output
    plan = json.loads(plan_result.output)
    assert plan["summary"] == {
        "create": 0,
        "update": 0,
        "delete": 0,
        "conflict": 0,
        "noop": 1,
    }
    assert plan["changes"][0]["kind"] == "noop"


def test_commander_msp_entry_points_raise_exact_capability_error() -> None:
    provider = CommanderCliProvider.__new__(CommanderCliProvider)

    with pytest.raises(CapabilityError) as discover_exc:
        provider.discover_managed_companies()
    with pytest.raises(CapabilityError) as apply_exc:
        provider.apply_msp_plan(Plan("msp-plan-test", [], []))

    assert discover_exc.value.reason == MSP_UNSUPPORTED
    assert apply_exc.value.reason == MSP_UNSUPPORTED
