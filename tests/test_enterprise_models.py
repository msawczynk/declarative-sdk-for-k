"""keeper-enterprise.v1 offline model round-trip and validate smoke tests.

Covers:
- Team manifest round-trip (load → dump → reload)
- Role manifest round-trip (load → dump → reload)
- Missing required field produces SchemaError
- ``dsk validate`` CLI against the enterprise-teams fixture exits 0
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_OK
from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.models_enterprise import (
    EnterpriseManifestV1,
    Role,
    Team,
    load_enterprise_manifest,
)
from keeper_sdk.core.schema import validate_manifest

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "examples"
    / "enterprise-teams"
    / "environment.yaml"
)

_NODE_REF = "keeper-enterprise:nodes:node.root"


def _team_doc() -> dict:
    return {
        "schema": "keeper-enterprise.v1",
        "nodes": [{"uid_ref": "node.root", "name": "Root"}],
        "teams": [
            {
                "uid_ref": "team.engineering",
                "name": "Engineering",
                "node_uid_ref": _NODE_REF,
                "restrict_edit": False,
                "restrict_share": True,
                "restrict_view": False,
            }
        ],
    }


def _role_doc() -> dict:
    return {
        "schema": "keeper-enterprise.v1",
        "nodes": [{"uid_ref": "node.root", "name": "Root"}],
        "roles": [
            {
                "uid_ref": "role.developer",
                "name": "Developer",
                "node_uid_ref": _NODE_REF,
                "visible_below": True,
                "new_user_inherit": False,
            }
        ],
    }


# ---------------------------------------------------------------------------
# round-trip tests


def test_team_manifest_roundtrip() -> None:
    """load → typed model → dump → reload must produce identical output."""
    doc = _team_doc()
    manifest = load_enterprise_manifest(doc)

    assert isinstance(manifest, EnterpriseManifestV1)
    assert len(manifest.teams) == 1
    team = manifest.teams[0]
    assert isinstance(team, Team)
    assert team.name == "Engineering"
    assert team.restrict_share is True

    dumped = manifest.model_dump(mode="json", exclude_none=True, by_alias=True)
    reloaded = load_enterprise_manifest(dumped)
    assert reloaded.model_dump(mode="json", exclude_none=True, by_alias=True) == dumped


def test_role_manifest_roundtrip() -> None:
    """load → typed model → dump → reload must produce identical output."""
    doc = _role_doc()
    manifest = load_enterprise_manifest(doc)

    assert isinstance(manifest, EnterpriseManifestV1)
    assert len(manifest.roles) == 1
    role = manifest.roles[0]
    assert isinstance(role, Role)
    assert role.name == "Developer"
    assert role.visible_below is True
    assert role.new_user_inherit is False

    dumped = manifest.model_dump(mode="json", exclude_none=True, by_alias=True)
    reloaded = load_enterprise_manifest(dumped)
    assert reloaded.model_dump(mode="json", exclude_none=True, by_alias=True) == dumped


# ---------------------------------------------------------------------------
# missing required field


def test_team_missing_name_raises_schema_error() -> None:
    doc = _team_doc()
    del doc["teams"][0]["name"]

    with pytest.raises(SchemaError) as exc:
        validate_manifest(doc)

    assert "name" in exc.value.reason


def test_role_missing_name_raises_schema_error() -> None:
    doc = _role_doc()
    del doc["roles"][0]["name"]

    with pytest.raises(SchemaError) as exc:
        validate_manifest(doc)

    assert "name" in exc.value.reason


# ---------------------------------------------------------------------------
# dsk validate CLI smoke test


def test_dsk_validate_enterprise_teams_fixture_exits_ok() -> None:
    """dsk validate against the enterprise-teams fixture must exit 0."""
    assert _FIXTURE_PATH.exists(), f"fixture missing: {_FIXTURE_PATH}"

    result = CliRunner().invoke(main, ["validate", str(_FIXTURE_PATH)], catch_exceptions=False)

    assert result.exit_code == EXIT_OK, f"dsk validate exited {result.exit_code}:\n{result.output}"
