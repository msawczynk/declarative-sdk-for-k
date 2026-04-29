"""P10 compatibility tests for keeper-vault-sharing.v1 schema, models, and plan."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.manifest import load_declarative_manifest_string
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.core.models_vault_sharing import (
    VAULT_SHARING_FAMILY,
    VaultSharingManifestV1,
    load_vault_sharing_manifest,
)
from keeper_sdk.core.schema import validate_manifest
from keeper_sdk.core.vault_sharing_plan import build_vault_sharing_plan
from keeper_sdk.providers import MockProvider

MANIFEST_NAME = "vault-sharing-p10"
SF_UID_REF = "sf.p10"
SF_REF = f"keeper-vault-sharing:shared_folders:{SF_UID_REF}"
REC_REF = "keeper-vault:records:rec.p10"
LABSHARE_EMAIL = "labshare@example.com"
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "keeper_sdk"
    / "core"
    / "schemas"
    / "vault_sharing"
    / "vault_sharing.v1.schema.json"
)


def _schema() -> dict[str, Any]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema


def _validate_schema(document: dict[str, Any]) -> None:
    validator = jsonschema.Draft202012Validator(
        _schema(), format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    if errors:
        raise AssertionError(errors[0].message)


def _shared_folder(
    uid_ref: str = SF_UID_REF,
    path: str = "/Shared/P10",
    *,
    manage_records: bool = True,
    manage_users: bool = False,
) -> dict[str, Any]:
    return {
        "uid_ref": uid_ref,
        "path": path,
        "defaults": {
            "manage_records": manage_records,
            "manage_users": manage_users,
            "can_edit": True,
            "can_share": False,
        },
    }


def _member(
    uid_ref: str = "sf.p10.user.labshare",
    *,
    user_email: str = LABSHARE_EMAIL,
    manage_records: bool = True,
    manage_users: bool = False,
) -> dict[str, Any]:
    return {
        "kind": "grantee",
        "uid_ref": uid_ref,
        "shared_folder_uid_ref": SF_REF,
        "grantee": {"kind": "user", "user_email": user_email},
        "permissions": {"manage_records": manage_records, "manage_users": manage_users},
    }


def _record_share(uid_ref: str = "rec.p10.user.labshare") -> dict[str, Any]:
    return {
        "uid_ref": uid_ref,
        "record_uid_ref": REC_REF,
        "user_email": LABSHARE_EMAIL,
        "permissions": {"can_edit": False, "can_share": False},
    }


def _full_doc() -> dict[str, Any]:
    return {
        "schema": VAULT_SHARING_FAMILY,
        "folders": [{"uid_ref": "folder.p10", "path": "/P10", "color": "blue"}],
        "shared_folders": [_shared_folder()],
        "share_records": [_record_share()],
        "share_folders": [_member()],
    }


def _manifest(document: dict[str, Any] | None = None) -> VaultSharingManifestV1:
    return load_vault_sharing_manifest(document or _full_doc())


def _member_live_record(
    *,
    uid_ref: str = "sf.p10.user.labshare",
    manage_records: bool = True,
    manage_users: bool = False,
    manifest_name: str = MANIFEST_NAME,
) -> LiveRecord:
    marker = encode_marker(
        uid_ref=uid_ref,
        manifest=manifest_name,
        resource_type="sharing_share_folder",
        parent_uid_ref=SF_REF,
    )
    payload = _member(uid_ref, manage_records=manage_records, manage_users=manage_users)
    return LiveRecord(
        keeper_uid=f"live-{uid_ref}",
        title=f"{SF_REF}:grantee:{LABSHARE_EMAIL}",
        resource_type="sharing_share_folder",
        payload=payload,
        marker=marker,
    )


def _shared_folder_live_record(
    *,
    manage_records: bool = False,
    manage_users: bool = False,
    manifest_name: str = MANIFEST_NAME,
) -> LiveRecord:
    marker = encode_marker(
        uid_ref=SF_UID_REF,
        manifest=manifest_name,
        resource_type="sharing_shared_folder",
    )
    payload = _shared_folder(manage_records=manage_records, manage_users=manage_users)
    return LiveRecord(
        keeper_uid=f"live-{SF_UID_REF}",
        title="/Shared/P10",
        resource_type="sharing_shared_folder",
        payload=payload,
        marker=marker,
    )


def test_alias_schema_file_is_valid_json_schema() -> None:
    assert _schema()["title"] == VAULT_SHARING_FAMILY


def test_schema_validates_minimal_manifest() -> None:
    _validate_schema({"schema": VAULT_SHARING_FAMILY})


def test_schema_validates_full_manifest() -> None:
    _validate_schema(_full_doc())


@pytest.mark.parametrize(
    ("mutator", "needle"),
    [
        (lambda doc: doc.pop("schema"), "'schema' is a required property"),
        (lambda doc: doc.update({"unexpected": True}), "Additional properties"),
        (lambda doc: doc["shared_folders"][0].update({"uid_ref": "-bad"}), "does not match"),
        (lambda doc: doc["share_folders"][0].pop("permissions"), "is not valid under"),
        (
            lambda doc: doc["share_records"][0].update({"record_uid_ref": "keeper-vault:x:bad"}),
            "does not match",
        ),
    ],
)
def test_schema_rejects_invalid_documents(mutator, needle: str) -> None:
    document = _full_doc()
    mutator(document)

    with pytest.raises(AssertionError, match=needle):
        _validate_schema(document)


def test_schema_rejects_invalid_email_format() -> None:
    document = _full_doc()
    document["share_folders"][0]["grantee"]["user_email"] = "not-an-email"

    with pytest.raises(AssertionError, match="not valid under"):
        _validate_schema(document)


def test_canonical_registry_still_accepts_keeper_vault_sharing_family() -> None:
    assert validate_manifest({"schema": VAULT_SHARING_FAMILY}) == VAULT_SHARING_FAMILY


def test_models_module_loads_empty_defaults() -> None:
    manifest = _manifest({"schema": VAULT_SHARING_FAMILY})

    assert manifest.vault_schema == VAULT_SHARING_FAMILY
    assert manifest.shared_folders == []
    assert manifest.share_folders == []


def test_models_module_loads_full_manifest() -> None:
    manifest = _manifest()

    assert manifest.shared_folders[0].uid_ref == SF_UID_REF
    assert manifest.share_folders[0].uid_ref == "sf.p10.user.labshare"


def test_manifest_dispatch_uses_vault_sharing_model_alias() -> None:
    loaded = load_declarative_manifest_string(json.dumps({"schema": VAULT_SHARING_FAMILY}))

    assert isinstance(loaded, VaultSharingManifestV1)


def test_plan_detects_new_shared_folder_membership() -> None:
    manifest = _manifest({"schema": VAULT_SHARING_FAMILY, "share_folders": [_member()]})

    plan = build_vault_sharing_plan(manifest, manifest_name=MANIFEST_NAME)

    assert [change.kind for change in plan.changes] == [ChangeKind.CREATE]
    assert plan.changes[0].resource_type == "sharing_share_folder"
    assert plan.creates[0].uid_ref == "sf.p10.user.labshare"


def test_plan_detects_shared_folder_member_permission_change() -> None:
    manifest = _manifest(
        {"schema": VAULT_SHARING_FAMILY, "share_folders": [_member(manage_records=True)]}
    )
    live = [_member_live_record(manage_records=False)]

    plan = build_vault_sharing_plan(manifest, live, manifest_name=MANIFEST_NAME)

    assert [change.kind for change in plan.changes] == [ChangeKind.UPDATE]
    assert plan.updates[0].before == {"manage_records": False}
    assert plan.updates[0].after == {"manage_records": True}


def test_plan_detects_removed_member_as_guarded_skip() -> None:
    manifest = _manifest({"schema": VAULT_SHARING_FAMILY})
    live = [_member_live_record()]

    plan = build_vault_sharing_plan(manifest, live, manifest_name=MANIFEST_NAME)

    assert [change.kind for change in plan.changes] == [ChangeKind.SKIP]
    assert "missing from manifest" in (plan.changes[0].reason or "")
    assert plan.is_clean


def test_plan_deletes_removed_member_when_allowed() -> None:
    manifest = _manifest({"schema": VAULT_SHARING_FAMILY})
    live = [_member_live_record()]

    plan = build_vault_sharing_plan(
        manifest,
        live,
        manifest_name=MANIFEST_NAME,
        allow_delete=True,
    )

    assert [change.kind for change in plan.changes] == [ChangeKind.DELETE]
    assert not plan.is_clean


def test_replan_after_mock_apply_is_noop() -> None:
    manifest = _manifest(
        {
            "schema": VAULT_SHARING_FAMILY,
            "shared_folders": [_shared_folder()],
            "share_folders": [_member()],
        }
    )
    provider = MockProvider(MANIFEST_NAME)

    create_plan = build_vault_sharing_plan(
        manifest, provider.discover(), manifest_name=MANIFEST_NAME
    )
    provider.apply_plan(create_plan)
    clean_plan = build_vault_sharing_plan(
        manifest, provider.discover(), manifest_name=MANIFEST_NAME
    )

    assert [outcome.action for outcome in provider.apply_plan(clean_plan)] == []
    assert clean_plan.changes == []
    assert clean_plan.is_clean


def test_plan_orders_shared_folder_before_membership() -> None:
    manifest = _manifest(
        {
            "schema": VAULT_SHARING_FAMILY,
            "shared_folders": [_shared_folder()],
            "share_folders": [_member()],
        }
    )

    plan = build_vault_sharing_plan(manifest, manifest_name=MANIFEST_NAME)

    assert [change.resource_type for change in plan.ordered()] == [
        "sharing_shared_folder",
        "sharing_share_folder",
    ]


def test_plan_detects_new_direct_record_share() -> None:
    manifest = _manifest({"schema": VAULT_SHARING_FAMILY, "share_records": [_record_share()]})

    plan = build_vault_sharing_plan(manifest, manifest_name=MANIFEST_NAME)

    assert [change.kind for change in plan.changes] == [ChangeKind.CREATE]
    assert plan.changes[0].resource_type == "sharing_record_share"


def test_plan_detects_shared_folder_default_permission_change() -> None:
    desired = _full_doc()
    desired["folders"] = []
    desired["share_records"] = []
    desired["share_folders"] = []
    manifest = _manifest(desired)
    live = [_shared_folder_live_record(manage_records=False)]

    plan = build_vault_sharing_plan(manifest, live, manifest_name=MANIFEST_NAME)

    assert [change.kind for change in plan.changes] == [ChangeKind.UPDATE]
    assert plan.updates[0].before == {"default_manage_records": False}
    assert plan.updates[0].after == {"default_manage_records": True}
