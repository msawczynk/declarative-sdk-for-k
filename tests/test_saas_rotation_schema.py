"""keeper-saas-rotation.v1 schema and typed-model scaffold tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.manifest import load_declarative_manifest_string
from keeper_sdk.core.models_saas_rotation import (
    SAAS_ROTATION_FAMILY,
    SaaSRotationManifestV1,
    load_saas_rotation_manifest,
)
from keeper_sdk.core.schema import load_schema_for_family, validate_manifest


def _doc() -> dict[str, Any]:
    return yaml.safe_load(
        Path("tests/fixtures/examples/saas-rotation/environment.yaml").read_text(encoding="utf-8")
    )


def test_saas_rotation_schema_is_packaged() -> None:
    schema = load_schema_for_family(SAAS_ROTATION_FAMILY)

    assert schema["title"] == SAAS_ROTATION_FAMILY
    assert schema["x-keeper-live-proof"]["status"] == "preview-gated"
    assert schema["properties"]["schema"]["const"] == SAAS_ROTATION_FAMILY


def test_saas_rotation_fixture_validates_and_loads_typed_model() -> None:
    document = _doc()

    assert validate_manifest(document) == SAAS_ROTATION_FAMILY
    loaded = load_declarative_manifest_string(json.dumps(document), suffix=".json")

    assert isinstance(loaded, SaaSRotationManifestV1)
    assert loaded.rotations[0].provider == "salesforce"
    assert loaded.bindings[0].record_uid_ref.endswith("rec.salesforce-admin")


def test_saas_rotation_loader_rejects_unknown_rotation_ref() -> None:
    document = _doc()
    document["bindings"][0]["rotation_uid_ref"] = "keeper-saas-rotation:rotations:rotation.missing"

    with pytest.raises(SchemaError) as exc:
        load_saas_rotation_manifest(document)

    assert "unknown SaaS rotation refs" in exc.value.reason
