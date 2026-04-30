"""keeper-workflow.v1 schema and typed-model scaffold tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.manifest import load_declarative_manifest_string
from keeper_sdk.core.models_workflow import (
    WORKFLOW_FAMILY,
    WorkflowManifestV1,
    load_workflow_manifest,
)
from keeper_sdk.core.schema import load_schema_for_family, validate_manifest


def _doc() -> dict[str, Any]:
    return yaml.safe_load(
        Path("tests/fixtures/examples/workflow/environment.yaml").read_text(encoding="utf-8")
    )


def test_workflow_schema_is_packaged() -> None:
    schema = load_schema_for_family(WORKFLOW_FAMILY)

    assert schema["title"] == WORKFLOW_FAMILY
    assert schema["x-keeper-live-proof"]["status"] == "preview-gated"
    assert schema["properties"]["schema"]["const"] == WORKFLOW_FAMILY


def test_workflow_fixture_validates_and_loads_typed_model() -> None:
    document = _doc()

    assert validate_manifest(document) == WORKFLOW_FAMILY
    loaded = load_declarative_manifest_string(json.dumps(document), suffix=".json")

    assert isinstance(loaded, WorkflowManifestV1)
    assert loaded.workflows[0].uid_ref == "workflow.break-glass"
    assert loaded.approvers[0].email == "security@example.com"


def test_workflow_loader_rejects_unknown_approver_ref() -> None:
    document = _doc()
    document["workflows"][0]["approver_uid_refs"] = ["keeper-workflow:approvers:approver.missing"]

    with pytest.raises(SchemaError) as exc:
        load_workflow_manifest(document)

    assert "unknown workflow approver refs" in exc.value.reason
