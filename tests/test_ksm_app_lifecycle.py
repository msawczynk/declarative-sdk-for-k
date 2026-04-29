"""Offline guardrails for declarative KSM app lifecycle support."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY, EXIT_SCHEMA


def _run(args: list[str]):
    return CliRunner().invoke(main, args, catch_exceptions=False)


def test_keeper_ksm_schema_only_validate_has_no_lifecycle_graph(tmp_path: Path) -> None:
    manifest = tmp_path / "ksm.yaml"
    manifest.write_text("schema: keeper-ksm.v1\n", encoding="utf-8")

    result = _run(["validate", str(manifest), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["family"] == "keeper-ksm.v1"
    assert payload["mode"] == "schema_only"
    assert payload["stages_completed"] == ["json_schema", "semantic_rules"]
    assert "uid_ref_count" not in payload


def test_keeper_ksm_lifecycle_body_is_rejected_until_modeled(tmp_path: Path) -> None:
    manifest = tmp_path / "ksm-app.yaml"
    manifest.write_text(
        """\
schema: keeper-ksm.v1
ksm_apps:
  - uid_ref: app.dsk
    name: dsk-service-admin
    shared_folders:
      - folder_uid_ref: keeper-vault-sharing:shared_folders:sf.ops
        editable: true
""",
        encoding="utf-8",
    )

    result = _run(["validate", str(manifest)])

    assert result.exit_code == EXIT_SCHEMA, result.output
    assert "ksm_apps" in result.output


def test_keeper_ksm_plan_and_cleanup_are_capability_gaps(tmp_path: Path) -> None:
    manifest = tmp_path / "ksm.yaml"
    manifest.write_text("schema: keeper-ksm.v1\n", encoding="utf-8")

    plan_result = _run(["--provider", "mock", "plan", str(manifest), "--json"])

    assert plan_result.exit_code == EXIT_CAPABILITY, plan_result.output
    assert "typed plan/load supports" in plan_result.output
    assert "keeper-ksm.v1" in plan_result.output
