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


@pytest.mark.parametrize(
    "bad_file",
    [
        "rbi-rotation-on.yaml",
        "env-field-mismatch.yaml",
        "gateway-create-in-unsupported-env.yaml",
    ],
)
def test_schema_rejects_invalid(invalid_manifest, bad_file: str) -> None:
    path = invalid_manifest(bad_file)
    with pytest.raises((SchemaError, CapabilityError)):
        load_manifest(path)


def test_missing_ref_detected(invalid_manifest) -> None:
    """Unknown uid_ref targets are caught at graph-build time."""
    from keeper_sdk.core import build_graph

    path = invalid_manifest("missing-ref.yaml")
    manifest = load_manifest(path)
    with pytest.raises(RefError):
        build_graph(manifest)


def test_duplicate_uid_ref_detected(invalid_manifest) -> None:
    from keeper_sdk.core import build_graph

    path = invalid_manifest("duplicate-uid-ref.yaml")
    manifest = load_manifest(path)
    with pytest.raises(RefError):
        build_graph(manifest)


def test_admin_cred_not_found_detected(invalid_manifest) -> None:
    from keeper_sdk.core import build_graph

    path = invalid_manifest("admin-cred-not-found.yaml")
    manifest = load_manifest(path)
    with pytest.raises(RefError):
        build_graph(manifest)


def test_gateway_create_requires_ksm(invalid_manifest) -> None:
    path = invalid_manifest("gateway-create-in-unsupported-env.yaml")
    with pytest.raises(CapabilityError):
        load_manifest(path)
