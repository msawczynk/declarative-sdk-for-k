"""CLI smoke tests."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY, EXIT_REF, EXIT_SCHEMA


def _run(args: list[str]):
    runner = CliRunner()
    return runner.invoke(main, args, catch_exceptions=False)


def test_validate_ok(minimal_manifest_path: Path) -> None:
    result = _run(["validate", str(minimal_manifest_path)])
    assert result.exit_code == 0, result.output
    assert "ok:" in result.output


def test_validate_rejects_missing_ref(invalid_manifest) -> None:
    path = invalid_manifest("missing-ref.yaml")
    result = _run(["validate", str(path)])
    assert result.exit_code == EXIT_REF


def test_validate_rejects_schema(invalid_manifest) -> None:
    path = invalid_manifest("rbi-rotation-on.yaml")
    result = _run(["validate", str(path)])
    assert result.exit_code == EXIT_SCHEMA


def test_validate_rejects_capability(invalid_manifest) -> None:
    path = invalid_manifest("gateway-create-in-unsupported-env.yaml")
    result = _run(["validate", str(path)])
    assert result.exit_code == EXIT_CAPABILITY


def test_plan_emits_json(minimal_manifest_path: Path) -> None:
    import json

    result = _run(["plan", str(minimal_manifest_path), "--json"])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.output)
    assert doc["manifest_name"] == "acme-lab-minimal"
    assert doc["summary"]["create"] >= 1


def test_apply_auto_approve(minimal_manifest_path: Path) -> None:
    result = _run(["apply", str(minimal_manifest_path), "--auto-approve"])
    assert result.exit_code == 0, result.output
    assert "create" in result.output.lower()
