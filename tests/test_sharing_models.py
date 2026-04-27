"""keeper-vault-sharing.v1 typed model tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.sharing_models import (
    SHARING_FAMILY,
    SharingManifestV1,
    load_sharing_manifest,
)


def _record_permissions(can_edit: bool = False, can_share: bool = False) -> dict[str, bool]:
    return {"can_edit": can_edit, "can_share": can_share}


def _folder_grantee_permissions(
    manage_records: bool = False,
    manage_users: bool = False,
) -> dict[str, bool]:
    return {"manage_records": manage_records, "manage_users": manage_users}


def test_sharing_manifest_empty_validates() -> None:
    manifest = load_sharing_manifest({"schema": SHARING_FAMILY})

    assert manifest.vault_schema == SHARING_FAMILY
    assert manifest.folders == []


def test_sharing_manifest_folder_validates_and_round_trips() -> None:
    manifest = load_sharing_manifest(
        {
            "schema": SHARING_FAMILY,
            "folders": [{"uid_ref": "folder.prod", "path": "/Prod", "color": "blue"}],
        }
    )

    dumped = manifest.model_dump(mode="python", by_alias=True, exclude_none=True)
    assert dumped["schema"] == SHARING_FAMILY
    assert dumped["folders"] == [{"uid_ref": "folder.prod", "path": "/Prod", "color": "blue"}]


def test_sharing_manifest_shared_folder_validates() -> None:
    manifest = load_sharing_manifest(
        {
            "schema": SHARING_FAMILY,
            "shared_folders": [
                {
                    "uid_ref": "sf.prod",
                    "path": "/Shared/Prod",
                    "defaults": {
                        "manage_users": False,
                        "manage_records": True,
                        "can_edit": True,
                        "can_share": False,
                    },
                }
            ],
        }
    )

    assert manifest.shared_folders[0].uid_ref == "sf.prod"


def test_sharing_manifest_record_share_validates() -> None:
    manifest = load_sharing_manifest(
        {
            "schema": SHARING_FAMILY,
            "share_records": [
                {
                    "uid_ref": "share.web-admin.platform",
                    "record_uid_ref": "keeper-vault:records:rec.web-admin",
                    "user_email": "platform@example.com",
                    "permissions": _record_permissions(),
                }
            ],
        }
    )

    assert manifest.share_records[0].record_uid_ref == "keeper-vault:records:rec.web-admin"


def test_sharing_manifest_share_folder_subtypes_validate() -> None:
    manifest = load_sharing_manifest(
        {
            "schema": SHARING_FAMILY,
            "shared_folders": [{"uid_ref": "sf.prod", "path": "/Shared/Prod"}],
            "share_folders": [
                {
                    "kind": "grantee",
                    "uid_ref": "sf.prod.team.ops",
                    "shared_folder_uid_ref": "keeper-vault-sharing:shared_folders:sf.prod",
                    "grantee": {
                        "kind": "team",
                        "team_uid_ref": "keeper-enterprise:teams:team.ops",
                    },
                    "permissions": _folder_grantee_permissions(),
                },
                {
                    "kind": "record",
                    "uid_ref": "sf.prod.record.web-admin",
                    "shared_folder_uid_ref": "keeper-vault-sharing:shared_folders:sf.prod",
                    "record_uid_ref": "keeper-vault:records:rec.web-admin",
                    "permissions": _record_permissions(),
                },
                {
                    "kind": "default",
                    "uid_ref": "sf.prod.default.grantee",
                    "shared_folder_uid_ref": "keeper-vault-sharing:shared_folders:sf.prod",
                    "target": "grantee",
                    "permissions": _folder_grantee_permissions(),
                },
            ],
        }
    )

    assert [share.kind for share in manifest.share_folders] == ["grantee", "record", "default"]


def test_load_sharing_manifest_schema_mismatch_raises_schema_error() -> None:
    with pytest.raises(SchemaError, match="expected 'keeper-vault-sharing.v1'"):
        load_sharing_manifest({"schema": "keeper-vault.v1", "records": []})


def test_sharing_manifest_unknown_top_level_key_rejected() -> None:
    with pytest.raises(ValidationError):
        SharingManifestV1.model_validate({"schema": SHARING_FAMILY, "unexpected": True})


def test_sharing_manifest_parent_folder_uid_ref_pattern_rejected() -> None:
    with pytest.raises(ValidationError):
        SharingManifestV1.model_validate(
            {
                "schema": SHARING_FAMILY,
                "folders": [
                    {
                        "uid_ref": "folder.child",
                        "path": "/Parent/Child",
                        "parent_folder_uid_ref": "folder.parent",
                    }
                ],
            }
        )


def test_sharing_manifest_record_ref_pattern_rejected() -> None:
    with pytest.raises(ValidationError):
        SharingManifestV1.model_validate(
            {
                "schema": SHARING_FAMILY,
                "share_records": [
                    {
                        "uid_ref": "share.bad",
                        "record_uid_ref": "records:rec.web-admin",
                        "user_email": "platform@example.com",
                        "permissions": _record_permissions(),
                    }
                ],
            }
        )


def test_sharing_manifest_grantee_cannot_have_user_and_team_refs() -> None:
    with pytest.raises(ValidationError):
        SharingManifestV1.model_validate(
            {
                "schema": SHARING_FAMILY,
                "share_folders": [
                    {
                        "kind": "grantee",
                        "uid_ref": "sf.prod.bad",
                        "shared_folder_uid_ref": "keeper-vault-sharing:shared_folders:sf.prod",
                        "grantee": {
                            "kind": "user",
                            "user_email": "platform@example.com",
                            "team_uid_ref": "keeper-enterprise:teams:team.ops",
                        },
                        "permissions": _folder_grantee_permissions(),
                    }
                ],
            }
        )
