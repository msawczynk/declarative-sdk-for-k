"""JSON Schema + semantic-rule validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from keeper_sdk.core import (
    CapabilityError,
    RefError,
    SchemaError,
    load_manifest,
)

_INVALID_DIR = (
    Path(__file__).resolve().parents[1].parent
    / "keeper-pam-declarative"
    / "examples"
    / "invalid"
)
_INVALID_FILES = sorted(p.name for p in _INVALID_DIR.glob("*.yaml"))


@pytest.mark.parametrize("bad_file", _INVALID_FILES)
def test_schema_rejects_invalid(invalid_manifest, bad_file: str) -> None:
    from keeper_sdk.core import build_graph

    path = invalid_manifest(bad_file)
    try:
        manifest = load_manifest(path)
    except (SchemaError, CapabilityError):
        return

    with pytest.raises(RefError):
        build_graph(manifest)
