"""keeper-privileged-access.v1 schema and typed-model scaffold tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.manifest import load_declarative_manifest_string
from keeper_sdk.core.models_privileged_access import (
    PRIVILEGED_ACCESS_FAMILY,
    PrivilegedAccessManifestV1,
    load_privileged_access_manifest,
)
from keeper_sdk.core.schema import load_schema_for_family, validate_manifest


def _doc() -> dict[str, Any]:
    return yaml.safe_load(
        Path("tests/fixtures/examples/privileged-access/environment.yaml").read_text(
            encoding="utf-8"
        )
    )


def test_privileged_access_schema_is_packaged() -> None:
    schema = load_schema_for_family(PRIVILEGED_ACCESS_FAMILY)

    assert schema["title"] == PRIVILEGED_ACCESS_FAMILY
    assert schema["x-keeper-live-proof"]["status"] == "preview-gated"
    assert schema["properties"]["schema"]["const"] == PRIVILEGED_ACCESS_FAMILY


def test_privileged_access_fixture_validates_and_loads_typed_model() -> None:
    document = _doc()

    assert validate_manifest(document) == PRIVILEGED_ACCESS_FAMILY
    loaded = load_declarative_manifest_string(json.dumps(document), suffix=".json")

    assert isinstance(loaded, PrivilegedAccessManifestV1)
    assert loaded.users[0].principal == "alice@example.com"
    assert loaded.group_memberships[0].group_uid_ref.endswith("group.break-glass")


def test_privileged_access_loader_rejects_unknown_group_ref() -> None:
    document = _doc()
    document["group_memberships"][0]["group_uid_ref"] = (
        "keeper-privileged-access:groups:group.missing"
    )

    with pytest.raises(SchemaError) as exc:
        load_privileged_access_manifest(document)

    assert "unknown privileged group refs" in exc.value.reason
