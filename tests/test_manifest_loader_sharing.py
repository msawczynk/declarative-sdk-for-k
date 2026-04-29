"""Manifest loader dispatch tests for keeper-vault-sharing.v1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from keeper_sdk.core.errors import ManifestError
from keeper_sdk.core.manifest import (
    load_declarative_manifest,
    load_declarative_manifest_string,
    load_manifest_string,
)
from keeper_sdk.core.sharing_models import SHARING_FAMILY, SharingManifestV1


def _sharing_doc() -> dict[str, object]:
    return {
        "schema": SHARING_FAMILY,
        "folders": [{"uid_ref": "folder.ops", "path": "/Operations"}],
        "shared_folders": [{"uid_ref": "sf.ops", "path": "/Shared/Operations"}],
        "share_records": [
            {
                "uid_ref": "share.admin.alice",
                "record_uid_ref": "keeper-vault:records:rec.admin",
                "user_email": "alice@example.com",
                "permissions": {"can_edit": False, "can_share": False},
            }
        ],
        "share_folders": [
            {
                "kind": "grantee",
                "uid_ref": "sf.ops.alice",
                "shared_folder_uid_ref": "keeper-vault-sharing:shared_folders:sf.ops",
                "grantee": {"kind": "user", "user_email": "alice@example.com"},
                "permissions": {"manage_records": True, "manage_users": False},
            }
        ],
    }


def _sharing_json() -> str:
    return json.dumps(_sharing_doc())


def test_load_declarative_manifest_string_accepts_sharing() -> None:
    manifest = load_declarative_manifest_string(_sharing_json(), suffix=".json")

    assert isinstance(manifest, SharingManifestV1)
    assert manifest.vault_schema == SHARING_FAMILY
    assert manifest.folders[0].uid_ref == "folder.ops"


def test_load_declarative_manifest_string_rejects_unplanned_family_names_all_supported() -> None:
    raw = '{"schema": "keeper-unknown-v99.v1"}'

    with pytest.raises(ManifestError) as exc:
        load_declarative_manifest_string(raw, suffix=".json")

    assert "keeper-unknown-v99.v1" in str(exc.value)


def test_load_manifest_string_rejects_sharing_as_pam_only() -> None:
    with pytest.raises(ManifestError) as exc:
        load_manifest_string(_sharing_json(), suffix=".json")

    assert "typed manifest load supports pam-environment.v1 only" in exc.value.reason


def test_load_declarative_manifest_reads_sharing_from_disk(tmp_path: Path) -> None:
    path = tmp_path / "sharing.yaml"
    path.write_text(f"schema: {SHARING_FAMILY}\n", encoding="utf-8")

    manifest = load_declarative_manifest(path)

    assert isinstance(manifest, SharingManifestV1)
    assert manifest.vault_schema == SHARING_FAMILY


def test_sharing_loader_round_trip_model_dump_idempotent() -> None:
    manifest = load_declarative_manifest_string(_sharing_json(), suffix=".json")
    assert isinstance(manifest, SharingManifestV1)
    dumped = manifest.model_dump(mode="json", by_alias=True, exclude_none=True)

    reloaded = load_declarative_manifest_string(json.dumps(dumped), suffix=".json")

    assert isinstance(reloaded, SharingManifestV1)
    assert reloaded.model_dump(mode="json", by_alias=True, exclude_none=True) == dumped
