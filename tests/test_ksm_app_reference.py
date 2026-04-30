"""Phase 7 KSM app reference_existing gateway coverage."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY, EXIT_CHANGES


def _run(args: list[str]):
    return CliRunner().invoke(main, args, catch_exceptions=False)


def _write_gateway_manifest(
    path: Path,
    *,
    mode: str = "reference_existing",
    include_ksm_application_name: bool = True,
) -> None:
    ksm_line = "    ksm_application_name: Edge KSM App\n" if include_ksm_application_name else ""
    path.write_text(
        f"""\
version: "1"
name: ksm-ref-existing
gateways:
  - uid_ref: gw.edge
    name: Edge Gateway
    mode: {mode}
{ksm_line}pam_configurations:
  - uid_ref: cfg.edge
    environment: local
    title: Edge PAM Config
    gateway_uid_ref: gw.edge
""",
        encoding="utf-8",
    )


def test_reference_existing_gateway_with_ksm_app_validates_and_plans(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pam.yaml"
    _write_gateway_manifest(path)

    validate_result = _run(["validate", str(path), "--json"])
    assert validate_result.exit_code == 0, validate_result.output
    validation = json.loads(validate_result.output)
    assert validation["family"] == "pam-environment.v1"
    assert validation["uid_ref_count"] == 2

    plan_result = _run(["plan", str(path), "--provider", "mock", "--json"])
    assert plan_result.exit_code == EXIT_CHANGES, plan_result.output
    plan = json.loads(plan_result.output)
    assert plan["summary"]["create"] == 1
    assert [change["resource_type"] for change in plan["changes"]] == ["pam_configuration"]
    assert plan["changes"][0]["after"]["gateway_uid_ref"] == "gw.edge"


def test_create_gateway_missing_ksm_app_is_caught_by_validate(tmp_path: Path) -> None:
    path = tmp_path / "pam.yaml"
    _write_gateway_manifest(path, mode="create", include_ksm_application_name=False)

    result = _run(["validate", str(path)])

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert "gateway mode='create' requires ksm_application_name" in result.output
