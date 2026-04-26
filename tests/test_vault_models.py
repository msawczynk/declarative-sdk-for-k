"""keeper-vault.v1 typed models (PR-V1)."""

from __future__ import annotations

import pytest

from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.manifest import load_declarative_manifest_string
from keeper_sdk.core.vault_models import (
    VAULT_FAMILY,
    VaultRecord,
    load_vault_manifest,
)


def test_vault_manifest_empty_roundtrip() -> None:
    doc = {"schema": "keeper-vault.v1", "records": []}
    m = load_vault_manifest(doc)
    assert m.vault_schema == VAULT_FAMILY
    assert m.records == []
    assert m.iter_uid_refs() == []


def test_vault_manifest_login_ok() -> None:
    doc = {
        "schema": "keeper-vault.v1",
        "records": [
            {
                "uid_ref": "rec.login-one",
                "type": "login",
                "title": "Lab Login",
                "fields": [{"type": "login", "label": "Login", "value": ["x"]}],
            }
        ],
    }
    m = load_vault_manifest(doc)
    assert len(m.records) == 1
    assert m.records[0].uid_ref == "rec.login-one"
    assert m.iter_uid_refs() == [("rec.login-one", "login")]


def test_vault_manifest_rejects_non_login_slice() -> None:
    doc = {
        "schema": "keeper-vault.v1",
        "records": [{"uid_ref": "a", "type": "pamMachine", "title": "nope"}],
    }
    with pytest.raises(SchemaError, match="L1 slice"):
        load_vault_manifest(doc)


def test_load_vault_manifest_rejects_pam_document() -> None:
    doc = {"version": "1", "name": "pam-only", "resources": []}
    with pytest.raises(SchemaError, match="pam-environment"):
        load_vault_manifest(doc)


def test_vault_record_model_direct() -> None:
    r = VaultRecord(uid_ref="r1", type="login", title="t")
    assert r.uid_ref == "r1"


def test_load_declarative_manifest_string_vault() -> None:
    raw = '{"schema": "keeper-vault.v1", "records": []}'
    m = load_declarative_manifest_string(raw, suffix=".json")
    assert m.vault_schema == VAULT_FAMILY
    assert m.records == []
