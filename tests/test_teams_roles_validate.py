"""Phase 7 teams/roles read-only validation contracts."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY, EXIT_OK, EXIT_SCHEMA
from keeper_sdk.core import SchemaError
from keeper_sdk.core.schema import PAM_FAMILY, validate_manifest


def _run(args: list[str]) -> Result:
    return CliRunner().invoke(main, args, catch_exceptions=False)


def _write_manifest(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _pam_machine_manifest() -> dict[str, object]:
    return {
        "version": "1",
        "name": "phase-7-teams-roles",
        "resources": [
            {
                "uid_ref": "res.machine",
                "type": "pamMachine",
                "title": "Linux Host",
                "host": "linux.example.com",
                "operating_system": "Linux",
            }
        ],
    }


@pytest.mark.parametrize("unknown_type", ["team", "role"])
def test_validate_rejects_unknown_pam_team_role_resource_types(
    tmp_path: Path,
    unknown_type: str,
) -> None:
    path = _write_manifest(
        tmp_path,
        f"{unknown_type}.yaml",
        "\n".join(
            [
                "version: '1'",
                "name: phase-7-teams-roles",
                "resources:",
                f"  - uid_ref: res.{unknown_type}",
                f"    type: {unknown_type}",
                f"    title: Platform {unknown_type.title()}",
                "",
            ]
        ),
    )

    result = _run(["validate", str(path)])

    assert result.exit_code == EXIT_SCHEMA, result.output
    assert "validation failed" in result.output
    assert unknown_type in result.output
    assert "not valid under any of the given schemas" in result.output


def test_validate_mixed_pam_machine_and_team_reports_team_schema_error() -> None:
    document = _pam_machine_manifest()

    assert validate_manifest(document) == PAM_FAMILY

    mixed = copy.deepcopy(document)
    resources = mixed["resources"]
    assert isinstance(resources, list)
    resources.append(
        {
            "uid_ref": "res.team",
            "type": "team",
            "title": "Platform Team",
        }
    )

    with pytest.raises(SchemaError) as exc:
        validate_manifest(mixed)

    assert exc.value.context["location"] == "resources/1"
    assert "team" in exc.value.reason


def test_enterprise_team_role_blocks_are_schema_only_empty_stubs() -> None:
    assert validate_manifest({"schema": "keeper-enterprise.v1", "teams": [], "roles": []}) == (
        "keeper-enterprise.v1"
    )


@pytest.mark.parametrize("collection", ["teams", "roles"])
def test_enterprise_team_role_blocks_reject_non_empty_resources(collection: str) -> None:
    document = {
        "schema": "keeper-enterprise.v1",
        collection: [{"uid_ref": f"{collection}.platform", "name": "Platform"}],
    }

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert exc.value.context["location"] == collection
    assert "expected to be empty" in exc.value.reason


def test_enterprise_online_validate_requires_commander_provider(
    tmp_path: Path,
) -> None:
    path = _write_manifest(
        tmp_path,
        "enterprise-empty-teams-roles.yaml",
        "schema: keeper-enterprise.v1\nteams: []\nroles: []\n",
    )

    result = _run(["validate", str(path), "--online"])

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert "--online" in result.output
    assert "--provider commander" in result.output


@pytest.mark.xfail(
    reason=(
        "Phase 7 live team/role reads require future keeper-enterprise validate --online "
        "discovery; offline worker must not touch a tenant."
    ),
    strict=True,
)
def test_future_validate_online_is_required_for_live_team_role_reads(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        "enterprise-empty-teams-roles.yaml",
        "schema: keeper-enterprise.v1\nteams: []\nroles: []\n",
    )

    result = _run(["validate", str(path), "--online", "--json"])

    assert result.exit_code == EXIT_OK, result.output
    payload = json.loads(result.output)
    assert payload["online"] is True
