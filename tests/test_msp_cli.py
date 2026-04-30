"""CLI coverage for msp-environment.v1 managed-company slice."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY, EXIT_CHANGES, EXIT_OK, EXIT_SCHEMA
from keeper_sdk.providers import MockProvider
from keeper_sdk.providers.commander_cli import CommanderCliProvider

cli_main_module = importlib.import_module("keeper_sdk.cli.main")


def _run(args: list[str]) -> Result:
    return CliRunner().invoke(main, args, catch_exceptions=False)


def _write_manifest(
    tmp_path: Path,
    *,
    seats: int = 5,
    manager: str | None = None,
) -> Path:
    lines = [
        "schema: msp-environment.v1",
        "name: msp-cli-test",
    ]
    if manager is not None:
        lines.append(f"manager: {manager}")
    lines.extend(
        [
            "managed_companies:",
            "  - name: Acme",
            "    plan: business",
            f"    seats: {seats}",
            "",
        ]
    )
    path = tmp_path / "msp.yaml"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_validate_accepts_msp_manifest_schema_family(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path)

    result = _run(["validate", str(path), "--json"])

    assert result.exit_code == EXIT_OK, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["family"] == "msp-environment.v1"
    assert payload["mode"] == "msp_offline"
    assert payload["managed_company_count"] == 1


def test_validate_msp_online_mock_runs_discover_and_diff(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path)

    result = _run(["validate", str(path), "--online", "--json"])

    assert result.exit_code == EXIT_OK, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "msp_online"
    assert payload["live_managed_company_count"] == 0
    assert payload["stage5_summary"]["create"] == 1


def test_validate_msp_online_commander_runs_discover(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_manifest(tmp_path)

    def _fake_discover(self: CommanderCliProvider) -> list[dict[str, Any]]:
        del self  # patched on class; no live Commander session in CI
        return []

    monkeypatch.setattr(CommanderCliProvider, "discover_managed_companies", _fake_discover)

    result = _run(["--provider", "commander", "validate", str(path), "--online", "--json"])

    assert result.exit_code == EXIT_OK, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "msp_online"
    assert payload["live_managed_company_count"] == 0


def test_plan_diff_apply_mock_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_manifest(tmp_path)
    provider = MockProvider("msp-cli-test")

    def provider_factory(manifest_name: str | None = None) -> MockProvider:
        return provider

    monkeypatch.setattr(cli_main_module, "MockProvider", provider_factory)

    plan_result = _run(["plan", str(path), "--provider", "mock", "--json"])
    assert plan_result.exit_code == EXIT_CHANGES, plan_result.output
    plan_payload = json.loads(plan_result.output)
    assert plan_payload["summary"]["create"] == 1

    diff_result = _run(["diff", str(path)])
    assert diff_result.exit_code == EXIT_CHANGES, diff_result.output
    assert "managed_company" in diff_result.output
    assert "Acme" in diff_result.output

    apply_result = _run(["apply", str(path), "--provider", "mock", "--yes"])
    assert apply_result.exit_code == EXIT_OK, apply_result.output
    assert provider.discover_managed_companies()[0]["name"] == "Acme"

    clean_plan_result = _run(["plan", str(path), "--provider", "mock", "--json"])
    assert clean_plan_result.exit_code == EXIT_OK, clean_plan_result.output
    clean_payload = json.loads(clean_plan_result.output)
    assert clean_payload["summary"]["noop"] == 1


def test_import_msp_manifest_adopts_unmanaged_mock_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_manifest(tmp_path, manager="keeper-msp-declarative")
    provider = MockProvider("msp-cli-test")
    provider.seed_managed_companies([{"name": "acme", "plan": "business", "seats": 5}])

    def provider_factory(manifest_name: str | None = None) -> MockProvider:
        return provider

    monkeypatch.setattr(cli_main_module, "MockProvider", provider_factory)

    result = _run(["import", str(path), "--auto-approve"])

    assert result.exit_code == EXIT_OK, result.output
    assert "marker_written=True" in result.output
    assert provider.discover_managed_companies()[0]["manager"] == "keeper-msp-declarative"


def test_import_msp_manifest_clean_plan_exits_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_manifest(tmp_path, manager="keeper-msp-declarative")
    provider = MockProvider("msp-cli-test")
    provider.seed_managed_companies(
        [
            {
                "name": "Acme",
                "plan": "business",
                "seats": 5,
                "manager": "keeper-msp-declarative",
            }
        ]
    )

    def provider_factory(manifest_name: str | None = None) -> MockProvider:
        return provider

    monkeypatch.setattr(cli_main_module, "MockProvider", provider_factory)

    result = _run(["import", str(path)])

    assert result.exit_code == EXIT_OK, result.output
    assert "no records to adopt." in result.output


def test_import_msp_manifest_commander_remains_capability_error(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path)

    result = _run(["--provider", "commander", "import", str(path)])

    assert result.exit_code == EXIT_CAPABILITY, result.output
    combined = result.output + result.stderr
    assert "MSP import and adoption are not implemented on commander provider" in combined


def test_validate_msp_rejects_case_insensitive_duplicate_mc_names(tmp_path: Path) -> None:
    path = tmp_path / "dup.yaml"
    path.write_text(
        "\n".join(
            [
                "schema: msp-environment.v1",
                "name: msp-cli-test",
                "managed_companies:",
                "  - name: Acme",
                "    plan: business",
                "    seats: 1",
                "  - name: acme",
                "    plan: enterprise",
                "    seats: 2",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = _run(["validate", str(path)])

    assert result.exit_code == EXIT_SCHEMA, result.output
    assert "rename one managed_company; names must be unique case-insensitively" in (
        result.output + result.stderr
    )


def test_plan_json_envelope_shape_remains_family_agnostic(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path)

    result = _run(["plan", str(path), "--provider", "mock", "--json"])

    assert result.exit_code == EXIT_CHANGES, result.output
    payload: dict[str, Any] = json.loads(result.output)
    assert set(payload) == {"manifest_name", "summary", "order", "changes"}
    assert set(payload["summary"]) == {"create", "update", "delete", "conflict", "noop"}
    assert set(payload["changes"][0]) == {
        "kind",
        "uid_ref",
        "resource_type",
        "title",
        "keeper_uid",
        "before",
        "after",
        "reason",
    }
    assert payload["changes"][0]["resource_type"] == "managed_company"
