"""Offline diff coverage for keeper-vault.v1 ``record_types[]``."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from keeper_sdk.core import compute_vault_diff, load_vault_manifest
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.core.vault_models import VaultManifestV1


def _record_type(uid_ref: str = "rt.service-login", description: str = "Service login") -> dict:
    return {
        "uid_ref": uid_ref,
        "scope": "enterprise",
        "record_type_id": 3000001,
        "content": {
            "$id": "serviceLogin",
            "categories": ["login"],
            "description": description,
            "fields": [
                {"$ref": "login", "required": True},
                {"$ref": "password", "required": True},
            ],
        },
    }


def _manifest(record_types: list[dict[str, Any]] | None = None) -> VaultManifestV1:
    return load_vault_manifest(
        {
            "schema": "keeper-vault.v1",
            "records": [],
            "record_types": record_types or [],
        }
    )


def _live_record_type(
    payload: dict[str, Any] | None = None,
    *,
    marker: dict[str, Any] | None = None,
    keeper_uid: str = "uid-record-type-1",
) -> dict[str, Any]:
    payload = payload or _record_type()
    if marker is None:
        marker = encode_marker(
            uid_ref=str(payload.get("uid_ref") or "rt.service-login"),
            manifest="demo",
            resource_type="record_type",
        )
    return {
        "keeper_uid": keeper_uid,
        "resource_type": "record_type",
        "title": "serviceLogin",
        "payload": payload,
        "marker": marker,
    }


def test_record_types_empty_manifest_and_live_no_changes() -> None:
    manifest = _manifest()

    changes = compute_vault_diff(manifest, [], live_record_type_defs=[])

    assert changes == []


def test_record_types_manifest_only_adds() -> None:
    manifest = _manifest([_record_type()])

    changes = compute_vault_diff(manifest, [], manifest_name="demo", live_record_type_defs=[])

    assert len(changes) == 1
    row = changes[0]
    assert row.kind is ChangeKind.ADD
    assert row.uid_ref == "rt.service-login"
    assert row.resource_type == "record_type"


def test_record_types_live_owned_orphan_deletes_when_allowed() -> None:
    manifest = _manifest()
    live = _live_record_type()

    changes = compute_vault_diff(
        manifest,
        [],
        manifest_name="demo",
        allow_delete=True,
        live_record_type_defs=[live],
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.DELETE
    assert changes[0].uid_ref == "rt.service-login"


def test_record_types_live_owned_orphan_skips_without_allow_delete() -> None:
    manifest = _manifest()
    live = _live_record_type()

    changes = compute_vault_diff(manifest, [], manifest_name="demo", live_record_type_defs=[live])

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.SKIP


def test_record_types_same_payload_no_changes() -> None:
    payload = _record_type()
    manifest = _manifest([payload])
    live = _live_record_type(copy.deepcopy(payload))

    changes = compute_vault_diff(manifest, [], manifest_name="demo", live_record_type_defs=[live])

    assert changes == []


def test_record_types_payload_drift_updates() -> None:
    desired = _record_type(description="Service login v2")
    live_payload = _record_type(description="Service login")
    manifest = _manifest([desired])
    live = _live_record_type(live_payload)

    changes = compute_vault_diff(manifest, [], manifest_name="demo", live_record_type_defs=[live])

    assert len(changes) == 1
    row = changes[0]
    assert row.kind is ChangeKind.UPDATE
    assert row.before["content"]["description"] == "Service login"
    assert row.after["content"]["description"] == "Service login v2"


def test_record_types_missing_id_falls_back_to_name() -> None:
    manifest = VaultManifestV1.model_validate(
        {
            "schema": "keeper-vault.v1",
            "record_types": [{"uid_ref": "rt.named", "name": "namedType"}],
        }
    )

    changes = compute_vault_diff(manifest, [], live_record_type_defs=[])

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.ADD
    assert changes[0].title == "namedType"


def test_record_types_missing_id_and_name_raises() -> None:
    manifest = VaultManifestV1.model_validate(
        {
            "schema": "keeper-vault.v1",
            "record_types": [{"uid_ref": "rt.bad", "content": {"fields": []}}],
        }
    )

    with pytest.raises(ValueError, match="record type definition missing"):
        compute_vault_diff(manifest, [], live_record_type_defs=[])


def test_record_types_live_unmanaged_skips() -> None:
    manifest = _manifest()
    live = _live_record_type(marker={})

    changes = compute_vault_diff(manifest, [], live_record_type_defs=[live])

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.SKIP
    assert changes[0].reason == "unmanaged record type"


def test_record_types_manifest_key_collision_raises() -> None:
    first = _record_type(uid_ref="rt.one")
    second = _record_type(uid_ref="rt.two")
    manifest = _manifest([first, second])

    with pytest.raises(ValueError, match="duplicate manifest record type key"):
        compute_vault_diff(manifest, [], live_record_type_defs=[])


def test_record_types_preserve_record_level_changes() -> None:
    manifest = load_vault_manifest(
        {
            "schema": "keeper-vault.v1",
            "records": [
                {
                    "uid_ref": "vault.login.alpha",
                    "type": "login",
                    "title": "Alpha",
                    "fields": [{"type": "login", "label": "Login", "value": ["u"]}],
                }
            ],
            "record_types": [_record_type()],
        }
    )

    changes = compute_vault_diff(manifest, [], manifest_name="demo", live_record_type_defs=[])

    assert len(changes) == 2
    assert {change.resource_type for change in changes} == {"login", "record_type"}
    assert {change.kind for change in changes} == {ChangeKind.CREATE}


def test_record_types_manifest_name_appears_in_change_rows() -> None:
    manifest = _manifest([_record_type()])

    changes = compute_vault_diff(
        manifest,
        [],
        manifest_name="customer-prod",
        live_record_type_defs=[],
    )

    assert changes[0].after["marker"]["manifest"] == "customer-prod"
