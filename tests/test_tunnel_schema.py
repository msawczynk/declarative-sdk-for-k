"""keeper-tunnel.v1 schema and typed-model scaffold tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.manifest import load_declarative_manifest_string
from keeper_sdk.core.models_tunnel import TUNNEL_FAMILY, TunnelManifestV1, load_tunnel_manifest
from keeper_sdk.core.schema import load_schema_for_family, validate_manifest


def _doc() -> dict[str, Any]:
    return yaml.safe_load(
        Path("tests/fixtures/examples/tunnel/environment.yaml").read_text(encoding="utf-8")
    )


def test_tunnel_schema_is_packaged() -> None:
    schema = load_schema_for_family(TUNNEL_FAMILY)

    assert schema["title"] == TUNNEL_FAMILY
    assert schema["x-keeper-live-proof"]["status"] == "preview-gated"
    assert schema["properties"]["schema"]["const"] == TUNNEL_FAMILY


def test_tunnel_fixture_validates_and_loads_typed_model() -> None:
    document = _doc()

    assert validate_manifest(document) == TUNNEL_FAMILY
    loaded = load_declarative_manifest_string(json.dumps(document), suffix=".json")

    assert isinstance(loaded, TunnelManifestV1)
    assert loaded.tunnels[0].protocol == "ssh"
    assert loaded.host_mappings[0].port == 22


def test_tunnel_loader_rejects_unknown_tunnel_ref() -> None:
    document = _doc()
    document["host_mappings"][0]["tunnel_uid_ref"] = "keeper-tunnel:tunnels:tunnel.missing"

    with pytest.raises(SchemaError) as exc:
        load_tunnel_manifest(document)

    assert "unknown tunnel refs" in exc.value.reason
