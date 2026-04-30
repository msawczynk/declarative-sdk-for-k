"""Offline guardrails for declarative KSM app lifecycle support."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY, EXIT_SCHEMA
from keeper_sdk.core.errors import CapabilityError

cli_main_module = importlib.import_module("keeper_sdk.cli.main")


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


def test_keeper_ksm_empty_plan_is_clean_for_mock_provider(tmp_path: Path) -> None:
    manifest = tmp_path / "ksm.yaml"
    manifest.write_text("schema: keeper-ksm.v1\n", encoding="utf-8")

    plan_result = _run(["--provider", "mock", "plan", str(manifest), "--json"])

    assert plan_result.exit_code == 0, plan_result.output
    assert json.loads(plan_result.output)["summary"] == {
        "create": 0,
        "update": 0,
        "delete": 0,
        "conflict": 0,
        "noop": 0,
    }


def test_keeper_ksm_commander_plan_without_discovery_exits_capability(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = tmp_path / "ksm.yaml"
    manifest.write_text("schema: keeper-ksm.v1\n", encoding="utf-8")

    class MissingCommanderProvider:
        def discover_ksm_state(self) -> dict[str, list[dict[str, object]]]:
            raise CapabilityError(
                reason="Commander KSM discovery unavailable",
                next_action="configure Commander before planning keeper-ksm.v1",
            )

    monkeypatch.setattr(
        cli_main_module, "_make_provider", lambda *args, **kwargs: MissingCommanderProvider()
    )
    plan_result = _run(["--provider", "commander", "plan", str(manifest), "--json"])

    assert plan_result.exit_code == EXIT_CAPABILITY, plan_result.output
    assert "discovery failed: Commander KSM discovery unavailable" in plan_result.output
