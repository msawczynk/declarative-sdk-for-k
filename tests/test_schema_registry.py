"""Multi-family schema registry (PAM parity program phase 0)."""

from __future__ import annotations

import pytest

from keeper_sdk.core.errors import ManifestError, SchemaError
from keeper_sdk.core.manifest import load_manifest_string, read_manifest_document_string
from keeper_sdk.core.schema import (
    PAM_FAMILY,
    load_schema_for_family,
    packaged_schema_families,
    resolve_manifest_family,
    validate_manifest,
)


def test_resolve_legacy_pam() -> None:
    doc = {"version": "1", "name": "demo", "resources": []}
    assert resolve_manifest_family(doc) == PAM_FAMILY


def test_resolve_explicit_pam_schema() -> None:
    doc = {"schema": "pam-environment.v1", "version": "1", "name": "demo", "resources": []}
    assert resolve_manifest_family(doc) == PAM_FAMILY


def test_resolve_vault() -> None:
    doc = {"schema": "keeper-vault.v1", "records": []}
    assert resolve_manifest_family(doc) == "keeper-vault.v1"


def test_unknown_schema() -> None:
    with pytest.raises(SchemaError, match="unknown manifest schema"):
        resolve_manifest_family({"schema": "keeper-foo.v1"})


def test_validate_minimal_keeper_vault() -> None:
    doc = {"schema": "keeper-vault.v1", "records": []}
    assert validate_manifest(doc) == "keeper-vault.v1"


def test_validate_dropped_posture_rejected() -> None:
    doc = {"schema": "keeper-security-posture.v1"}
    with pytest.raises(SchemaError, match="dropped-design"):
        validate_manifest(doc)


def test_packaged_families_include_core_set() -> None:
    keys = set(packaged_schema_families())
    assert PAM_FAMILY in keys
    assert "keeper-vault.v1" in keys
    assert "keeper-security-posture.v1" in keys


def test_load_schema_for_family_roundtrip() -> None:
    pam = load_schema_for_family(PAM_FAMILY)
    assert pam["title"]
    vault = load_schema_for_family("keeper-vault.v1")
    assert vault["properties"]["schema"]["const"] == "keeper-vault.v1"


def test_load_manifest_rejects_non_pam() -> None:
    raw = '{"schema": "keeper-vault.v1", "records": []}'
    with pytest.raises(ManifestError, match="typed manifest load supports"):
        load_manifest_string(raw, suffix=".json", validate=True)


def test_load_manifest_string_non_pam_validate_false_still_pydantic_fails() -> None:
    raw = '{"schema": "keeper-vault.v1", "records": []}'
    with pytest.raises(Exception):
        load_manifest_string(raw, suffix=".json", validate=False)


def test_read_manifest_document_string_vault() -> None:
    raw = "schema: keeper-vault.v1\nrecords: []\n"
    doc = read_manifest_document_string(raw, suffix=".yaml")
    assert doc["schema"] == "keeper-vault.v1"
