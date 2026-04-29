"""keeper-vault-sharing.v1 sibling-block MockProvider round-trip tests."""

from __future__ import annotations

from typing import Any

import pytest

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.interfaces import ApplyOutcome, LiveRecord
from keeper_sdk.core.metadata import (
    MANAGER_NAME,
    MARKER_FIELD_LABEL,
    encode_marker,
    serialize_marker,
)
from keeper_sdk.core.planner import build_plan
from keeper_sdk.core.sharing_diff import (
    _RECORD_SHARE_RESOURCE,
    _SHARE_FOLDER_RESOURCE,
    _SHARED_FOLDER_RESOURCE,
    _SHARING_FOLDER_RESOURCE,
    compute_sharing_diff,
)
from keeper_sdk.core.sharing_models import (
    SHARING_FAMILY,
    SharingManifestV1,
    load_sharing_manifest,
)
from keeper_sdk.providers import MockProvider

MANIFEST_NAME = "vault-sharing"
SF_REF = "keeper-vault-sharing:shared_folders:sf.prod"
REC_REF = "keeper-vault:records:rec.web"


def _folder(uid_ref: str = "folder.prod", path: str = "/Prod") -> dict[str, Any]:
    return {"uid_ref": uid_ref, "path": path, "color": "blue"}


def _shared_folder(
    uid_ref: str = "sf.prod",
    path: str = "/Shared/Prod",
    *,
    defaults: dict[str, bool] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {"uid_ref": uid_ref, "path": path}
    if defaults is not None:
        data["defaults"] = defaults
    return data


def _record_share(
    uid_ref: str = "share.web.platform",
    record_uid_ref: str = REC_REF,
    user_email: str = "platform@example.com",
    *,
    can_edit: bool = True,
    can_share: bool = False,
    expires_at: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "uid_ref": uid_ref,
        "record_uid_ref": record_uid_ref,
        "user_email": user_email,
        "permissions": {"can_edit": can_edit, "can_share": can_share},
    }
    if expires_at is not None:
        data["expires_at"] = expires_at
    return data


def _grantee_share(
    uid_ref: str = "sf.prod.user.platform",
    *,
    user_email: str = "platform@example.com",
    manage_records: bool = True,
    manage_users: bool = False,
    expires_at: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "kind": "grantee",
        "uid_ref": uid_ref,
        "shared_folder_uid_ref": SF_REF,
        "grantee": {"kind": "user", "user_email": user_email},
        "permissions": {"manage_records": manage_records, "manage_users": manage_users},
    }
    if expires_at is not None:
        data["expires_at"] = expires_at
    return data


def _sf_record_share(
    uid_ref: str = "sf.prod.record.web",
    *,
    record_uid_ref: str = REC_REF,
    can_edit: bool = True,
    can_share: bool = False,
    expires_at: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "kind": "record",
        "uid_ref": uid_ref,
        "shared_folder_uid_ref": SF_REF,
        "record_uid_ref": record_uid_ref,
        "permissions": {"can_edit": can_edit, "can_share": can_share},
    }
    if expires_at is not None:
        data["expires_at"] = expires_at
    return data


def _default_share(
    uid_ref: str = "sf.prod.default.grantee",
    *,
    target: str = "grantee",
    manage_records: bool = True,
    manage_users: bool = False,
    can_edit: bool = True,
    can_share: bool = False,
) -> dict[str, Any]:
    if target == "record":
        permissions = {"can_edit": can_edit, "can_share": can_share}
    else:
        permissions = {"manage_records": manage_records, "manage_users": manage_users}
    return {
        "kind": "default",
        "uid_ref": uid_ref,
        "shared_folder_uid_ref": SF_REF,
        "target": target,
        "permissions": permissions,
    }


def _manifest(
    *,
    folders: list[dict[str, Any]] | None = None,
    shared_folders: list[dict[str, Any]] | None = None,
    share_records: list[dict[str, Any]] | None = None,
    share_folders: list[dict[str, Any]] | None = None,
) -> SharingManifestV1:
    return load_sharing_manifest(
        {
            "schema": SHARING_FAMILY,
            "folders": folders or [],
            "shared_folders": shared_folders or [],
            "share_records": share_records or [],
            "share_folders": share_folders or [],
        }
    )


def _live_row(record: LiveRecord) -> dict[str, Any]:
    return {
        "keeper_uid": record.keeper_uid,
        "resource_type": record.resource_type,
        "title": record.title,
        "payload": dict(record.payload),
        "marker": dict(record.marker) if record.marker else None,
    }


def _to_live_folders(records: list[LiveRecord]) -> list[dict[str, Any]]:
    return [
        _live_row(record) for record in records if record.resource_type == _SHARING_FOLDER_RESOURCE
    ]


def _to_live_shared_folders(records: list[LiveRecord]) -> list[dict[str, Any]]:
    return [
        _live_row(record) for record in records if record.resource_type == _SHARED_FOLDER_RESOURCE
    ]


def _to_live_share_records(records: list[LiveRecord]) -> list[dict[str, Any]]:
    rows = [
        _live_row(record) for record in records if record.resource_type == _RECORD_SHARE_RESOURCE
    ]
    for record in records:
        payload_rows = record.payload.get("record_shares")
        if isinstance(payload_rows, list):
            rows.extend(dict(row) for row in payload_rows if isinstance(row, dict))
    return rows


def _to_live_share_folders(records: list[LiveRecord]) -> list[dict[str, Any]]:
    rows = [
        _live_row(record) for record in records if record.resource_type == _SHARE_FOLDER_RESOURCE
    ]
    for record in records:
        for payload_key in ("share_folder_grants", "share_folders"):
            payload_rows = record.payload.get(payload_key)
            if isinstance(payload_rows, list):
                rows.extend(dict(row) for row in payload_rows if isinstance(row, dict))
    return rows


def _sharing_order(manifest: SharingManifestV1) -> list[str]:
    return [
        *(folder.uid_ref for folder in manifest.folders),
        *(folder.uid_ref for folder in manifest.shared_folders),
        *(share.uid_ref for share in manifest.share_records),
        *(share.uid_ref for share in manifest.share_folders),
    ]


def _changes(
    manifest: SharingManifestV1,
    provider: MockProvider,
    *,
    allow_delete: bool = False,
) -> list[Change]:
    records = provider.discover()
    return compute_sharing_diff(
        manifest,
        _to_live_folders(records),
        manifest_name=MANIFEST_NAME,
        allow_delete=allow_delete,
        live_shared_folders=_to_live_shared_folders(records),
        live_share_records=_to_live_share_records(records),
        live_share_folders=_to_live_share_folders(records),
    )


def _apply(
    provider: MockProvider,
    manifest: SharingManifestV1,
    changes: list[Change],
    *,
    dry_run: bool = False,
) -> list[ApplyOutcome]:
    return provider.apply_plan(
        build_plan(MANIFEST_NAME, changes, _sharing_order(manifest)),
        dry_run=dry_run,
    )


def _actionable(changes: list[Change]) -> list[Change]:
    return [
        change
        for change in changes
        if change.kind
        in (ChangeKind.CREATE, ChangeKind.UPDATE, ChangeKind.DELETE, ChangeKind.CONFLICT)
    ]


def _marker(
    uid_ref: str,
    resource_type: str,
    *,
    parent_uid_ref: str | None = None,
    manifest_name: str = MANIFEST_NAME,
    manager: str = MANAGER_NAME,
) -> dict[str, Any]:
    marker = encode_marker(
        uid_ref=uid_ref,
        manifest=manifest_name,
        resource_type=resource_type,
        parent_uid_ref=parent_uid_ref,
    )
    marker["manager"] = manager
    return marker


def _payload_with_marker(payload: dict[str, Any], marker: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    custom_fields = dict(out.get("custom_fields") or {})
    custom_fields[MARKER_FIELD_LABEL] = serialize_marker(marker)
    out["custom_fields"] = custom_fields
    return out


def _seed(
    provider: MockProvider,
    *,
    uid_ref: str,
    resource_type: str,
    title: str,
    payload: dict[str, Any],
    parent_uid_ref: str | None = None,
    manager: str = MANAGER_NAME,
) -> str:
    marker = _marker(
        uid_ref,
        resource_type,
        parent_uid_ref=parent_uid_ref,
        manager=manager,
    )
    keeper_uid = f"live-{uid_ref}"
    provider.seed(
        [
            LiveRecord(
                keeper_uid=keeper_uid,
                title=title,
                resource_type=resource_type,
                payload=_payload_with_marker(payload, marker),
                marker=marker,
            )
        ]
    )
    return keeper_uid


def _seed_shared_folder(
    provider: MockProvider,
    uid_ref: str = "sf.prod",
    *,
    name: str = "/Shared/Prod",
    default_manage_records: bool = True,
    default_manage_users: bool = False,
    default_can_edit: bool = True,
    default_can_share: bool = False,
    manager: str = MANAGER_NAME,
) -> str:
    return _seed(
        provider,
        uid_ref=uid_ref,
        resource_type=_SHARED_FOLDER_RESOURCE,
        title=name,
        payload={
            "uid_ref": uid_ref,
            "name": name,
            "default_manage_records": default_manage_records,
            "default_manage_users": default_manage_users,
            "default_can_edit": default_can_edit,
            "default_can_share": default_can_share,
        },
        manager=manager,
    )


def _seed_record_share(
    provider: MockProvider,
    share: dict[str, Any] | None = None,
    *,
    manager: str = MANAGER_NAME,
) -> str:
    payload = dict(share or _record_share())
    return _seed(
        provider,
        uid_ref=str(payload["uid_ref"]),
        resource_type=_RECORD_SHARE_RESOURCE,
        title=f"{payload['record_uid_ref']}:{payload['user_email']}",
        payload=payload,
        parent_uid_ref=str(payload["record_uid_ref"]),
        manager=manager,
    )


def _seed_share_folder(
    provider: MockProvider,
    share: dict[str, Any] | None = None,
    *,
    manager: str = MANAGER_NAME,
) -> str:
    payload = dict(share or _grantee_share())
    return _seed(
        provider,
        uid_ref=str(payload["uid_ref"]),
        resource_type=_SHARE_FOLDER_RESOURCE,
        title=f"{payload['shared_folder_uid_ref']}:{payload['kind']}",
        payload=payload,
        parent_uid_ref=str(payload["shared_folder_uid_ref"]),
        manager=manager,
    )


def test_shared_folder_create_discover_rediff_clean() -> None:
    manifest = _manifest(shared_folders=[_shared_folder()])
    provider = MockProvider(MANIFEST_NAME)

    changes = _changes(manifest, provider)
    outcomes = _apply(provider, manifest, changes)
    clean_changes = _changes(manifest, provider)
    [record] = _to_live_shared_folders(provider.discover())

    assert [change.kind for change in changes] == [ChangeKind.CREATE]
    assert [outcome.action for outcome in outcomes] == ["create"]
    assert record["marker"]["manager"] == MANAGER_NAME
    assert _actionable(clean_changes) == []


def test_shared_folder_update_name_and_default_can_edit() -> None:
    manifest = _manifest(
        shared_folders=[
            _shared_folder(
                path="/Shared/Prod New",
                defaults={
                    "manage_records": True,
                    "manage_users": False,
                    "can_edit": False,
                    "can_share": False,
                },
            )
        ]
    )
    provider = MockProvider(MANIFEST_NAME)
    _seed_shared_folder(provider, name="/Shared/Prod", default_can_edit=True)

    changes = _changes(manifest, provider)
    outcomes = _apply(provider, manifest, changes)
    [record] = _to_live_shared_folders(provider.discover())

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.UPDATE
    assert outcomes[0].action == "update"
    assert record["payload"]["name"] == "/Shared/Prod New"
    assert record["payload"]["default_can_edit"] is False


def test_shared_folder_delete_when_allowed() -> None:
    manifest = _manifest()
    provider = MockProvider(MANIFEST_NAME)
    _seed_shared_folder(provider)

    changes = _changes(manifest, provider, allow_delete=True)
    outcomes = _apply(provider, manifest, changes)

    assert [change.kind for change in changes] == [ChangeKind.DELETE]
    assert [outcome.action for outcome in outcomes] == ["delete"]
    assert _to_live_shared_folders(provider.discover()) == []


def test_shared_folder_unmanaged_is_skipped_without_mutation() -> None:
    manifest = _manifest(shared_folders=[_shared_folder()])
    provider = MockProvider(MANIFEST_NAME)
    _seed_shared_folder(provider, manager="other-manager")

    changes = _changes(manifest, provider)
    outcomes = _apply(provider, manifest, changes)

    assert [change.kind for change in changes] == [ChangeKind.SKIP]
    assert changes[0].reason == "unmanaged shared_folder"
    assert outcomes == []
    assert len(_to_live_shared_folders(provider.discover())) == 1


def test_record_share_create_discover_rediff_clean() -> None:
    manifest = _manifest(share_records=[_record_share()])
    provider = MockProvider(MANIFEST_NAME)

    changes = _changes(manifest, provider)
    outcomes = _apply(provider, manifest, changes)
    clean_changes = _changes(manifest, provider)
    live = _to_live_share_records(provider.discover())

    assert [change.kind for change in changes] == [ChangeKind.CREATE]
    assert [outcome.action for outcome in outcomes] == ["create"]
    assert len(live) == 1
    assert _actionable(clean_changes) == []


def test_record_share_update_permission_drift() -> None:
    manifest = _manifest(share_records=[_record_share(can_edit=False)])
    provider = MockProvider(MANIFEST_NAME)
    _seed_record_share(provider, _record_share(can_edit=True))

    changes = _changes(manifest, provider)
    outcomes = _apply(provider, manifest, changes)
    [row] = _to_live_share_records(provider.discover())

    assert [change.kind for change in changes] == [ChangeKind.UPDATE]
    assert [outcome.action for outcome in outcomes] == ["update"]
    assert row["payload"]["can_edit"] is False
    assert _actionable(_changes(manifest, provider)) == []


def test_record_share_delete_when_allowed() -> None:
    manifest = _manifest()
    provider = MockProvider(MANIFEST_NAME)
    _seed_record_share(provider)

    changes = _changes(manifest, provider, allow_delete=True)
    outcomes = _apply(provider, manifest, changes)

    assert [change.kind for change in changes] == [ChangeKind.DELETE]
    assert [outcome.action for outcome in outcomes] == ["delete"]
    assert _to_live_share_records(provider.discover()) == []


def test_record_share_grantee_key_disambiguates_same_record() -> None:
    manifest = _manifest(
        share_records=[
            _record_share(uid_ref="share.web.a", user_email="a@example.com"),
            _record_share(uid_ref="share.web.b", user_email="b@example.com"),
        ]
    )
    provider = MockProvider(MANIFEST_NAME)

    changes = _changes(manifest, provider)
    outcomes = _apply(provider, manifest, changes)
    live = _to_live_share_records(provider.discover())

    assert [change.kind for change in changes] == [ChangeKind.CREATE, ChangeKind.CREATE]
    assert [outcome.action for outcome in outcomes] == ["create", "create"]
    assert {row["payload"]["user_email"] for row in live} == {"a@example.com", "b@example.com"}
    assert _actionable(_changes(manifest, provider)) == []


def test_share_folder_grantee_create_discover_rediff_clean() -> None:
    manifest = _manifest(share_folders=[_grantee_share()])
    provider = MockProvider(MANIFEST_NAME)

    changes = _changes(manifest, provider)
    outcomes = _apply(provider, manifest, changes)

    assert [change.kind for change in changes] == [ChangeKind.CREATE]
    assert [outcome.action for outcome in outcomes] == ["create"]
    assert len(_to_live_share_folders(provider.discover())) == 1
    assert _actionable(_changes(manifest, provider)) == []


def test_share_folder_grantee_update_permission_drift() -> None:
    manifest = _manifest(share_folders=[_grantee_share(manage_records=False)])
    provider = MockProvider(MANIFEST_NAME)
    _seed_share_folder(provider, _grantee_share(manage_records=True))

    changes = _changes(manifest, provider)
    outcomes = _apply(provider, manifest, changes)
    [row] = _to_live_share_folders(provider.discover())

    assert [change.kind for change in changes] == [ChangeKind.UPDATE]
    assert [outcome.action for outcome in outcomes] == ["update"]
    assert row["payload"]["manage_records"] is False


def test_share_folder_grantee_delete_when_allowed() -> None:
    manifest = _manifest()
    provider = MockProvider(MANIFEST_NAME)
    _seed_share_folder(provider, _grantee_share())

    changes = _changes(manifest, provider, allow_delete=True)
    outcomes = _apply(provider, manifest, changes)

    assert [change.kind for change in changes] == [ChangeKind.DELETE]
    assert [outcome.action for outcome in outcomes] == ["delete"]
    assert _to_live_share_folders(provider.discover()) == []


def test_share_folder_record_create_discover_rediff_clean() -> None:
    manifest = _manifest(share_folders=[_sf_record_share()])
    provider = MockProvider(MANIFEST_NAME)

    changes = _changes(manifest, provider)
    outcomes = _apply(provider, manifest, changes)

    assert [change.kind for change in changes] == [ChangeKind.CREATE]
    assert [outcome.action for outcome in outcomes] == ["create"]
    assert len(_to_live_share_folders(provider.discover())) == 1
    assert _actionable(_changes(manifest, provider)) == []


def test_share_folder_record_update_permission_drift() -> None:
    manifest = _manifest(share_folders=[_sf_record_share(can_share=True)])
    provider = MockProvider(MANIFEST_NAME)
    _seed_share_folder(provider, _sf_record_share(can_share=False))

    changes = _changes(manifest, provider)
    outcomes = _apply(provider, manifest, changes)
    [row] = _to_live_share_folders(provider.discover())

    assert [change.kind for change in changes] == [ChangeKind.UPDATE]
    assert [outcome.action for outcome in outcomes] == ["update"]
    assert row["payload"]["can_share"] is True


def test_share_folder_record_delete_when_allowed() -> None:
    manifest = _manifest()
    provider = MockProvider(MANIFEST_NAME)
    _seed_share_folder(provider, _sf_record_share())

    changes = _changes(manifest, provider, allow_delete=True)
    outcomes = _apply(provider, manifest, changes)

    assert [change.kind for change in changes] == [ChangeKind.DELETE]
    assert [outcome.action for outcome in outcomes] == ["delete"]
    assert _to_live_share_folders(provider.discover()) == []


def test_share_folder_default_create_discover_rediff_clean() -> None:
    manifest = _manifest(share_folders=[_default_share()])
    provider = MockProvider(MANIFEST_NAME)

    changes = _changes(manifest, provider)
    outcomes = _apply(provider, manifest, changes)

    assert [change.kind for change in changes] == [ChangeKind.CREATE]
    assert [outcome.action for outcome in outcomes] == ["create"]
    assert len(_to_live_share_folders(provider.discover())) == 1
    assert _actionable(_changes(manifest, provider)) == []


def test_share_folder_default_update_permission_drift() -> None:
    manifest = _manifest(share_folders=[_default_share(manage_users=True)])
    provider = MockProvider(MANIFEST_NAME)
    _seed_share_folder(provider, _default_share(manage_users=False))

    changes = _changes(manifest, provider)
    outcomes = _apply(provider, manifest, changes)
    [row] = _to_live_share_folders(provider.discover())

    assert [change.kind for change in changes] == [ChangeKind.UPDATE]
    assert [outcome.action for outcome in outcomes] == ["update"]
    assert row["payload"]["manage_users"] is True


def test_share_folder_default_collision_raises() -> None:
    manifest = _manifest(
        share_folders=[
            _default_share(uid_ref="sf.prod.default.grantee", target="grantee"),
            _default_share(uid_ref="sf.prod.default.record", target="record"),
        ]
    )

    with pytest.raises(ValueError, match="duplicate manifest share_folder key"):
        compute_sharing_diff(manifest, live_share_folders=[])


def test_mixed_sharing_manifest_round_trips_clean() -> None:
    manifest = _manifest(
        folders=[_folder("folder.prod", "/Prod"), _folder("folder.ops", "/Ops")],
        shared_folders=[_shared_folder()],
        share_records=[_record_share()],
        share_folders=[
            _grantee_share(uid_ref="sf.prod.user.platform"),
            _default_share(uid_ref="sf.prod.default.grantee"),
        ],
    )
    provider = MockProvider(MANIFEST_NAME)

    create_changes = _changes(manifest, provider)
    outcomes = _apply(provider, manifest, create_changes)
    clean_changes = _changes(manifest, provider)

    assert [change.kind for change in create_changes] == [
        ChangeKind.CREATE,
        ChangeKind.CREATE,
        ChangeKind.CREATE,
        ChangeKind.CREATE,
        ChangeKind.CREATE,
        ChangeKind.CREATE,
    ]
    assert [outcome.action for outcome in outcomes] == [
        "create",
        "create",
        "create",
        "create",
        "create",
        "create",
    ]
    assert _actionable(clean_changes) == []


@pytest.mark.parametrize(
    "manifest",
    [
        _manifest(shared_folders=[_shared_folder()]),
        _manifest(share_records=[_record_share()]),
        _manifest(share_folders=[_grantee_share()]),
    ],
)
def test_sibling_dry_run_reports_outcome_without_state_change(
    manifest: SharingManifestV1,
) -> None:
    provider = MockProvider(MANIFEST_NAME)

    changes = _changes(manifest, provider)
    outcomes = _apply(provider, manifest, changes, dry_run=True)

    assert [change.kind for change in changes] == [ChangeKind.CREATE]
    assert [outcome.action for outcome in outcomes] == ["create"]
    assert outcomes[0].details["dry_run"] is True
    assert provider.discover() == []
