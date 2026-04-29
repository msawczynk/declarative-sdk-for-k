"""Offline smoke coverage for the CLI adoption lifecycle."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

_SMOKE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "smoke"
sys.path.insert(0, str(_SMOKE_DIR))

import scenarios as smoke_scenarios  # noqa: E402

from keeper_sdk.cli import main  # noqa: E402
from keeper_sdk.core import (  # noqa: E402
    build_graph,
    build_plan,
    compute_diff,
    execution_order,
)
from keeper_sdk.core.diff import ChangeKind  # noqa: E402
from keeper_sdk.core.manifest import load_manifest  # noqa: E402
from keeper_sdk.providers import MockProvider  # noqa: E402

cli_main_module = importlib.import_module("keeper_sdk.cli.main")

TITLE_PREFIX = "sdk-smoke"


def _write_manifest(tmp_path: Path) -> tuple[smoke_scenarios.AdoptionScenarioSpec, Path]:
    scenario = smoke_scenarios.adoption_get("pamAdoption")
    path = tmp_path / "pamAdoption.yaml"
    path.write_text(
        yaml.safe_dump(scenario.build_manifest(TITLE_PREFIX), sort_keys=False),
        encoding="utf-8",
    )
    return scenario, path


def _seed_provider(
    scenario: smoke_scenarios.AdoptionScenarioSpec, manifest_name: str
) -> MockProvider:
    provider = MockProvider(manifest_name)
    provider.seed(scenario.seed_records(TITLE_PREFIX))
    return provider


def _run(args: list[str]):
    runner = CliRunner()
    return runner.invoke(main, args, catch_exceptions=False)


def test_adoption_scenario_is_registered() -> None:
    assert "pamAdoption" in smoke_scenarios.adoption_names()
    assert smoke_scenarios.adoption_get("pamAdoption") in smoke_scenarios.all_adoption_scenarios()


def test_import_dry_run_shows_adoption_rows_without_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, manifest_path = _write_manifest(tmp_path)
    manifest = load_manifest(manifest_path)
    provider = _seed_provider(scenario, manifest.name)
    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    result = _run(["import", str(manifest_path), "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "update" in result.output
    assert "adoption:" in result.output
    assert "~1 update" in result.output
    assert provider.discover()[0].marker is None


def test_import_auto_approve_writes_marker_and_replans_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, manifest_path = _write_manifest(tmp_path)
    manifest = load_manifest(manifest_path)
    provider = _seed_provider(scenario, manifest.name)
    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    result = _run(["import", str(manifest_path), "--auto-approve"])

    assert result.exit_code == 0, result.output
    scenario.verify(provider.discover(), TITLE_PREFIX, manifest.name)

    order = execution_order(build_graph(manifest))
    replan = build_plan(manifest.name, compute_diff(manifest, provider.discover()), order)
    assert not [change for change in replan.changes if change.kind is not ChangeKind.NOOP]
