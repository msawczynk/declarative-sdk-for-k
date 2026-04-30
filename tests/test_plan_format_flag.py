"""CLI coverage for the transitional ``dsk plan --format`` flag."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY, EXIT_CHANGES


def _run(args: list[str]):
    return CliRunner().invoke(main, args, catch_exceptions=False)


def test_plan_format_json_routes_to_existing_json_renderer(minimal_manifest_path: Path) -> None:
    result = _run(["plan", str(minimal_manifest_path), "--format", "json"])

    assert result.exit_code == EXIT_CHANGES, result.output
    payload = json.loads(result.output)
    assert payload["manifest_name"] == "acme-lab-minimal"
    assert set(payload["summary"]) == {"create", "update", "delete", "conflict", "noop"}


def test_plan_format_table_routes_to_existing_table_renderer(minimal_manifest_path: Path) -> None:
    result = _run(["plan", str(minimal_manifest_path), "--format", "table"])

    assert result.exit_code == EXIT_CHANGES, result.output
    assert "create" in result.output
    assert "acme-lab-minimal" in result.output


def test_plan_format_backstage_is_capability_stub(minimal_manifest_path: Path) -> None:
    result = _run(["plan", str(minimal_manifest_path), "--format", "backstage"])

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert "capability error" in result.output
    assert "plan output format `backstage` is not implemented" in result.output
    assert "--format json" in result.output
