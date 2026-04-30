"""keeper-enterprise.v1 offline import path coverage."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CONFLICT, EXIT_OK
from keeper_sdk.core.metadata import MANAGER_NAME
from keeper_sdk.providers import MockProvider

cli_main_module = importlib.import_module("keeper_sdk.cli.main")

MANIFEST_NAME = "enterprise"


def _run(args: list[str]):
    return CliRunner().invoke(main, args, catch_exceptions=False)


def _doc() -> dict[str, Any]:
    return {
        "schema": "keeper-enterprise.v1",
        "nodes": [{"uid_ref": "node.root", "name": "Root"}],
        "users": [
            {
                "uid_ref": "user.alice",
                "email": "alice@example.com",
                "node_uid_ref": "keeper-enterprise:nodes:node.root",
            }
        ],
    }


def _write_manifest(tmp_path: Path, document: dict[str, Any] | None = None) -> Path:
    path = tmp_path / "enterprise.yaml"
    path.write_text(yaml.safe_dump(document or _doc(), sort_keys=False), encoding="utf-8")
    return path


def _live_from_doc(document: dict[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    source = document or _doc()
    return {
        "nodes": [dict(row) for row in source.get("nodes", [])],
        "users": [dict(row) for row in source.get("users", [])],
        "roles": [dict(row) for row in source.get("roles", [])],
        "teams": [dict(row) for row in source.get("teams", [])],
        "enforcements": [dict(row) for row in source.get("enforcements", [])],
        "aliases": [dict(row) for row in source.get("aliases", [])],
    }


def test_enterprise_import_plan_shows_unmanaged_records_and_writes_markers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = _write_manifest(tmp_path)
    provider = MockProvider(MANIFEST_NAME)
    provider.seed_enterprise_state(_live_from_doc())
    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    result = _run(["--provider", "mock", "import", str(path), "--auto-approve"])

    assert result.exit_code == EXIT_OK, result.output
    assert "node.root" in result.output
    assert "user.alice" in result.output
    assert "~2 update" in result.output
    assert "marker_written=True" in result.output
    markers = provider.enterprise_markers()
    assert len(markers) == 2
    assert {marker["manager"] for marker in markers.values()} == {MANAGER_NAME}


def test_enterprise_import_conflicts_on_already_managed_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = _write_manifest(tmp_path)
    live = _live_from_doc()
    live["users"][0]["manager"] = "other-manager"
    provider = MockProvider(MANIFEST_NAME)
    provider.seed_enterprise_state(live)
    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    result = _run(["--provider", "mock", "import", str(path), "--auto-approve"])
    combined = result.output + getattr(result, "stderr", "")

    assert result.exit_code == EXIT_CONFLICT, combined
    assert "managed by other manager" in combined
    markers = provider.enterprise_markers()
    assert len(markers) == 1
    assert next(iter(markers.values()))["manager"] == "other-manager"


def test_enterprise_import_dry_run_shows_plan_without_writing_markers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = _write_manifest(tmp_path)
    provider = MockProvider(MANIFEST_NAME)
    provider.seed_enterprise_state(_live_from_doc())
    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    result = _run(["--provider", "mock", "import", str(path), "--dry-run"])

    assert result.exit_code == EXIT_OK, result.output
    assert "node.root" in result.output
    assert "user.alice" in result.output
    assert "~2 update" in result.output
    assert provider.enterprise_markers() == {}
