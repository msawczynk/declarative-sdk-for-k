"""CLI dispatch tests for keeper-vault-sharing.v1."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CHANGES, EXIT_SCHEMA
from keeper_sdk.core import load_declarative_manifest, load_manifest
from keeper_sdk.core.errors import ManifestError
from keeper_sdk.core.sharing_models import SHARING_FAMILY, SharingManifestV1
from keeper_sdk.providers import MockProvider

cli_main_module = importlib.import_module("keeper_sdk.cli.main")

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "examples" / "sharing.example.yaml"
SHARING_SCHEMA = (
    REPO_ROOT
    / "keeper_sdk"
    / "core"
    / "schemas"
    / "keeper-vault-sharing"
    / "keeper-vault-sharing.v1.schema.json"
)


def _run(args: list[str]):
    return CliRunner().invoke(main, args, catch_exceptions=False)


def _copy_example(tmp_path: Path) -> Path:
    path = tmp_path / "sharing.yaml"
    path.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def test_validate_sharing_example_mentions_family() -> None:
    result = _run(["validate", str(EXAMPLE)])

    assert result.exit_code == 0, result.output
    assert SHARING_FAMILY in result.output


def test_validate_sharing_rejects_unknown_field(tmp_path: Path) -> None:
    path = tmp_path / "bad-sharing.yaml"
    path.write_text(f"schema: {SHARING_FAMILY}\nunexpected: true\n", encoding="utf-8")

    result = _run(["validate", str(path)])

    assert result.exit_code == EXIT_SCHEMA, result.output
    assert "validation failed" in result.output


def test_plan_sharing_example_mock_creates_all_blocks() -> None:
    result = _run(["plan", str(EXAMPLE), "--provider", "mock", "--json"])

    assert result.exit_code == EXIT_CHANGES, result.output
    plan = json.loads(result.output)
    assert plan["summary"]["create"] == 4
    assert {change["resource_type"] for change in plan["changes"]} == {
        "sharing_folder",
        "sharing_shared_folder",
        "sharing_record_share",
        "sharing_share_folder",
    }


def test_apply_sharing_example_mock_yes_succeeds() -> None:
    result = _run(["apply", str(EXAMPLE), "--provider", "mock", "--yes"])

    assert result.exit_code == 0, result.output
    assert "create" in result.output.lower()


def test_apply_then_plan_sharing_mock_is_clean(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = _copy_example(tmp_path)
    provider = MockProvider(path.stem)
    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

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
        "noop": 0,
    }
    assert plan["changes"] == []


def test_clean_sharing_plan_allow_delete_stays_clean(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = _copy_example(tmp_path)
    provider = MockProvider(path.stem)
    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    apply_result = _run(["apply", str(path), "--provider", "mock", "--yes"])
    assert apply_result.exit_code == 0, apply_result.output

    plan_result = _run(["plan", str(path), "--provider", "mock", "--allow-delete", "--json"])
    assert plan_result.exit_code == 0, plan_result.output
    plan = json.loads(plan_result.output)
    assert plan["summary"]["create"] == 0
    assert plan["summary"]["delete"] == 0
    assert plan["changes"] == []


def test_empty_sharing_manifest_after_apply_skips_or_deletes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = _copy_example(tmp_path)
    provider = MockProvider(path.stem)
    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    apply_result = _run(["apply", str(path), "--provider", "mock", "--yes"])
    assert apply_result.exit_code == 0, apply_result.output
    path.write_text(f"schema: {SHARING_FAMILY}\n", encoding="utf-8")

    skip_result = _run(["plan", str(path), "--provider", "mock", "--json"])
    assert skip_result.exit_code == 0, skip_result.output
    skip_plan = json.loads(skip_result.output)
    assert [change["kind"] for change in skip_plan["changes"]] == ["skip"] * 4

    delete_result = _run(["plan", str(path), "--provider", "mock", "--allow-delete", "--json"])
    assert delete_result.exit_code == EXIT_CHANGES, delete_result.output
    delete_plan = json.loads(delete_result.output)
    assert delete_plan["summary"]["delete"] == 4
    assert [change["kind"] for change in delete_plan["changes"]] == ["delete"] * 4


def test_load_declarative_manifest_returns_sharing_model(tmp_path: Path) -> None:
    path = _copy_example(tmp_path)

    manifest = load_declarative_manifest(path)

    assert isinstance(manifest, SharingManifestV1)
    assert manifest.vault_schema == SHARING_FAMILY


def test_load_manifest_rejects_sharing_entrypoint(tmp_path: Path) -> None:
    path = _copy_example(tmp_path)

    try:
        load_manifest(path)
    except ManifestError as exc:
        assert "typed manifest load supports pam-environment.v1 only" in exc.reason
    else:  # pragma: no cover
        raise AssertionError("load_manifest accepted keeper-vault-sharing.v1")


def test_sharing_schema_live_proof_status_stays_scaffold_only() -> None:
    schema = json.loads(SHARING_SCHEMA.read_text(encoding="utf-8"))

    assert schema["x-keeper-live-proof"]["status"] == "scaffold-only"
