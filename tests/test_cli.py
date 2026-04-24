"""CLI smoke tests."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY, EXIT_CHANGES, EXIT_CONFLICT, EXIT_REF, EXIT_SCHEMA
from keeper_sdk.core import build_graph, build_plan, compute_diff, execution_order, load_manifest
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.providers import MockProvider

cli_main_module = importlib.import_module("keeper_sdk.cli.main")


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


@pytest.mark.parametrize(
    ("scenario", "expected_exit"),
    [
        ("clean", 0),
        ("changes", EXIT_CHANGES),
        ("conflict", EXIT_CONFLICT),
    ],
)
def test_plan_emits_json_exit_codes(
    minimal_manifest_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    expected_exit: int,
) -> None:
    manifest = load_manifest(minimal_manifest_path)
    provider = MockProvider(manifest.name)

    if scenario == "clean":
        graph = build_graph(manifest)
        order = execution_order(graph)
        provider.apply_plan(build_plan(manifest.name, compute_diff(manifest, provider.discover()), order))
    elif scenario == "conflict":
        provider.seed(
            [
                LiveRecord(
                    keeper_uid="LIVE_UID",
                    title="lab-linux-1",
                    resource_type="pamMachine",
                    marker={
                        **encode_marker(
                            uid_ref="acme-lab-linux1",
                            manifest=manifest.name,
                            resource_type="pamMachine",
                        ),
                        "manager": "someone-else",
                    },
                    payload={"title": "lab-linux-1"},
                )
            ]
        )

    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    result = _run(["plan", str(minimal_manifest_path), "--json"])
    assert result.exit_code == expected_exit, result.output
    doc = json.loads(result.output)
    assert doc["manifest_name"] == "acme-lab-minimal"
    if scenario == "clean":
        assert doc["summary"] == {"create": 0, "update": 0, "delete": 0, "conflict": 0, "noop": 3}
    elif scenario == "changes":
        assert doc["summary"]["create"] >= 1
        assert doc["summary"]["conflict"] == 0
    else:
        assert doc["summary"]["conflict"] >= 1


def test_apply_auto_approve(minimal_manifest_path: Path) -> None:
    result = _run(["apply", str(minimal_manifest_path), "--auto-approve"])
    assert result.exit_code == 0, result.output
    assert "create" in result.output.lower()
