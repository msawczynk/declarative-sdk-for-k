"""keeper-terraform.v1 schema, typed model, and CLI boundary tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY
from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.manifest import load_declarative_manifest_string
from keeper_sdk.core.models_terraform import (
    TERRAFORM_FAMILY,
    TerraformIntegrationManifestV1,
    load_terraform_manifest,
)
from keeper_sdk.core.schema import load_schema_for_family, validate_manifest


def _doc() -> dict[str, Any]:
    return {
        "schema": TERRAFORM_FAMILY,
        "resource_mappings": [
            {
                "dsk_family": "keeper-vault.v1",
                "tf_resource_type": "secretsmanager_login",
                "direction": "bidirectional",
            },
            {
                "dsk_family": "pam-environment.v1",
                "tf_resource_type": "secretsmanager_pam_machine",
                "direction": "tf_source",
            },
            {
                "dsk_family": "keeper-enterprise.v1",
                "tf_resource_type": "keeper_role_enforcements",
                "direction": "dsk_source",
            },
        ],
    }


def _write_manifest(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "terraform.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_terraform_schema_is_packaged_under_keeper_terraform_path() -> None:
    schema = load_schema_for_family(TERRAFORM_FAMILY)

    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert schema["title"] == TERRAFORM_FAMILY
    assert schema["x-keeper-live-proof"]["status"] == "upstream-gap"
    assert "resource_mappings" in schema["properties"]


def test_terraform_validate_accepts_resource_mappings() -> None:
    assert validate_manifest(_doc()) == TERRAFORM_FAMILY


def test_terraform_loader_returns_typed_model() -> None:
    loaded = load_declarative_manifest_string(json.dumps(_doc()), suffix=".json")

    assert isinstance(loaded, TerraformIntegrationManifestV1)
    assert loaded.resource_mappings[0].dsk_family == "keeper-vault.v1"
    assert loaded.resource_mappings[0].direction == "bidirectional"


def test_terraform_invalid_direction_is_rejected() -> None:
    document = _doc()
    document["resource_mappings"][0]["direction"] = "terraform_first"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "not one of" in exc.value.reason


def test_terraform_invalid_dsk_family_is_rejected() -> None:
    document = _doc()
    document["resource_mappings"][0]["dsk_family"] = "keeper-unknown.v1"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert exc.value.context["location"] == "resource_mappings/0/dsk_family"


def test_terraform_rejects_unknown_mapping_property() -> None:
    document = _doc()
    document["resource_mappings"][0]["provider_alias"] = "keeper.prod"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "Additional properties" in exc.value.reason


def test_terraform_loader_rejects_duplicate_resource_mapping() -> None:
    document = _doc()
    document["resource_mappings"].append(dict(document["resource_mappings"][0]))

    with pytest.raises(SchemaError) as exc:
        load_terraform_manifest(document)

    assert "duplicate resource_mappings" in exc.value.reason


def test_terraform_plan_cli_exits_capability_error(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _doc())

    result = CliRunner().invoke(main, ["plan", str(path), "--json"], catch_exceptions=False)

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert TERRAFORM_FAMILY in result.output
    assert "upstream-gap" in result.output


def test_terraform_apply_cli_exits_capability_error(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _doc())

    result = CliRunner().invoke(main, ["apply", str(path), "--dry-run"], catch_exceptions=False)

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert TERRAFORM_FAMILY in result.output
    assert "upstream-gap" in result.output
