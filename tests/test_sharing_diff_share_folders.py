"""keeper-vault-sharing.v1 ``share_folders[]`` sibling-block diff tests."""

from __future__ import annotations

import pytest

from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.errors import OwnershipError
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.core.sharing_diff import compute_sharing_diff
from keeper_sdk.core.sharing_models import SHARING_FAMILY, SharingManifestV1

_SF_REF = "keeper-vault-sharing:shared_folders:sf.prod"
_REC_REF = "keeper-vault:records:rec.web"


def _grantee_share(
    uid_ref: str = "sf.prod.user.platform",
    *,
    user_email: str = "platform@example.com",
    manage_records: bool = True,
    manage_users: bool = False,
    expires_at: str | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "kind": "grantee",
        "uid_ref": uid_ref,
        "shared_folder_uid_ref": _SF_REF,
        "grantee": {"kind": "user", "user_email": user_email},
        "permissions": {"manage_records": manage_records, "manage_users": manage_users},
    }
    if expires_at is not None:
        data["expires_at"] = expires_at
    return data


def _record_share(
    uid_ref: str = "sf.prod.record.web",
    *,
    record_uid_ref: str = _REC_REF,
    can_edit: bool = True,
    can_share: bool = False,
    expires_at: str | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "kind": "record",
        "uid_ref": uid_ref,
        "shared_folder_uid_ref": _SF_REF,
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
) -> dict[str, object]:
    permissions: dict[str, bool]
    if target == "record":
        permissions = {"can_edit": can_edit, "can_share": can_share}
    else:
        permissions = {"manage_records": manage_records, "manage_users": manage_users}
    return {
        "kind": "default",
        "uid_ref": uid_ref,
        "shared_folder_uid_ref": _SF_REF,
        "target": target,
        "permissions": permissions,
    }


def _manifest(*share_folders: dict[str, object]) -> SharingManifestV1:
    return SharingManifestV1.model_validate(
        {"schema": SHARING_FAMILY, "share_folders": list(share_folders)}
    )


def _marker(
    uid_ref: str,
    *,
    manifest_name: str = "vault-sharing",
    manager: str | None = None,
    version: str | None = None,
) -> dict[str, object]:
    marker = encode_marker(
        uid_ref=uid_ref,
        manifest=manifest_name,
        resource_type="sharing_share_folder",
        parent_uid_ref=_SF_REF,
    )
    if manager is not None:
        marker["manager"] = manager
    if version is not None:
        marker["version"] = version
    return marker


def _live_share_folder(
    payload: dict[str, object] | None = None,
    *,
    marker: dict[str, object] | None = None,
) -> dict[str, object]:
    data = dict(payload or _grantee_share())
    uid_ref = str(data["uid_ref"])
    data["keeper_uid"] = f"live-{uid_ref}"
    data["marker"] = marker if marker is not None else _marker(uid_ref)
    return data


@pytest.mark.parametrize("share", [_grantee_share(), _record_share(), _default_share()])
def test_share_folders_each_subtype_manifest_only_adds(share: dict[str, object]) -> None:
    changes = compute_sharing_diff(_manifest(share), live_share_folders=[])

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.ADD
    assert changes[0].resource_type == "sharing_share_folder"


@pytest.mark.parametrize("share", [_grantee_share(), _record_share(), _default_share()])
def test_share_folders_each_subtype_live_owned_orphan_deletes_when_allowed(
    share: dict[str, object],
) -> None:
    changes = compute_sharing_diff(
        _manifest(),
        live_share_folders=[_live_share_folder(share)],
        allow_delete=True,
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.DELETE


@pytest.mark.parametrize("share", [_grantee_share(), _record_share(), _default_share()])
def test_share_folders_each_subtype_live_owned_orphan_skips_without_allow_delete(
    share: dict[str, object],
) -> None:
    changes = compute_sharing_diff(_manifest(), live_share_folders=[_live_share_folder(share)])

    assert len(changes) == 1
    if share["kind"] == "record":
        assert changes[0].kind is ChangeKind.CONFLICT
        assert (
            changes[0].reason == "managed share_folder record member missing from manifest; "
            "pass --allow-delete to remove"
        )
    else:
        assert changes[0].kind is ChangeKind.SKIP
        assert changes[0].reason == "managed share_folder missing from manifest"


@pytest.mark.parametrize(
    ("desired", "live", "field", "before", "after"),
    [
        (_grantee_share(manage_records=False), _grantee_share(), "manage_records", True, False),
        (_record_share(can_share=True), _record_share(), "can_share", False, True),
        (
            _default_share(target="record", can_edit=False),
            _default_share(target="grantee"),
            "target",
            "grantee",
            "record",
        ),
    ],
)
def test_share_folders_each_subtype_drift_updates(
    desired: dict[str, object],
    live: dict[str, object],
    field: str,
    before: object,
    after: object,
) -> None:
    changes = compute_sharing_diff(
        _manifest(desired),
        live_share_folders=[_live_share_folder(live)],
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.UPDATE
    assert changes[0].before[field] == before
    assert changes[0].after[field] == after


def test_share_folders_same_fields_no_changes() -> None:
    changes = compute_sharing_diff(
        _manifest(_grantee_share()),
        live_share_folders=[_live_share_folder(_grantee_share())],
    )

    assert changes == []


def test_share_folders_live_unmanaged_skips() -> None:
    live = _live_share_folder(
        _grantee_share(),
        marker=_marker("sf.prod.user.platform", manager="other-manager"),
    )

    changes = compute_sharing_diff(_manifest(_grantee_share()), live_share_folders=[live])

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.SKIP
    assert changes[0].reason == "unmanaged share_folder"


def test_share_folders_default_unique_per_shared_folder() -> None:
    manifest = _manifest(
        _default_share(uid_ref="sf.prod.default.grantee", target="grantee"),
        _default_share(uid_ref="sf.prod.default.record", target="record"),
    )

    with pytest.raises(ValueError, match="duplicate manifest share_folder key"):
        compute_sharing_diff(manifest, live_share_folders=[])


def test_share_folders_subtype_switch_is_add_and_delete_when_allowed() -> None:
    changes = compute_sharing_diff(
        _manifest(_record_share(uid_ref="sf.prod.member")),
        live_share_folders=[_live_share_folder(_grantee_share(uid_ref="sf.prod.member"))],
        allow_delete=True,
    )

    assert [change.kind for change in changes] == [ChangeKind.ADD, ChangeKind.DELETE]


def test_share_folders_marker_version_mismatch_raises() -> None:
    live = _live_share_folder(
        _grantee_share(),
        marker=_marker("sf.prod.user.platform", version="9999"),
    )

    with pytest.raises(OwnershipError, match="marker version 9999"):
        compute_sharing_diff(_manifest(), live_share_folders=[live])


def test_share_folders_manifest_name_propagates_to_change_rows() -> None:
    changes = compute_sharing_diff(
        _manifest(_grantee_share()),
        live_share_folders=[],
        manifest_name="customer-prod",
    )

    assert len(changes) == 1
    assert changes[0].manifest_name == "customer-prod"
    assert changes[0].after["marker"]["manifest"] == "customer-prod"
