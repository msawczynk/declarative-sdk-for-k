"""keeper-vault-sharing.v1 ``shared_folders[]`` sibling-block diff tests."""

from __future__ import annotations

import pytest

from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.errors import OwnershipError
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.core.sharing_diff import compute_sharing_diff
from keeper_sdk.core.sharing_models import SHARING_FAMILY, SharingManifestV1


def _shared_folder(
    uid_ref: str = "sf.prod",
    path: str = "/Shared/Prod",
    *,
    defaults: dict[str, bool] | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {"uid_ref": uid_ref, "path": path}
    if defaults is not None:
        data["defaults"] = defaults
    return data


def _folder(uid_ref: str = "folder.prod", path: str = "/Prod") -> dict[str, object]:
    return {"uid_ref": uid_ref, "path": path}


def _manifest(
    *shared_folders: dict[str, object],
    folders: list[dict[str, object]] | None = None,
) -> SharingManifestV1:
    return SharingManifestV1.model_validate(
        {
            "schema": SHARING_FAMILY,
            "folders": folders or [],
            "shared_folders": list(shared_folders),
        }
    )


def _marker(
    uid_ref: str = "sf.prod",
    *,
    manifest_name: str = "vault-sharing",
    manager: str | None = None,
    version: str | None = None,
) -> dict[str, object]:
    marker = encode_marker(
        uid_ref=uid_ref,
        manifest=manifest_name,
        resource_type="sharing_shared_folder",
    )
    if manager is not None:
        marker["manager"] = manager
    if version is not None:
        marker["version"] = version
    return marker


def _live_shared_folder(
    uid_ref: str = "sf.prod",
    name: str = "/Shared/Prod",
    *,
    default_manage_records: bool = True,
    default_manage_users: bool = False,
    default_can_edit: bool = True,
    default_can_share: bool = False,
    marker: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "keeper_uid": f"live-{uid_ref}",
        "uid_ref": uid_ref,
        "name": name,
        "default_manage_records": default_manage_records,
        "default_manage_users": default_manage_users,
        "default_can_edit": default_can_edit,
        "default_can_share": default_can_share,
        "marker": marker if marker is not None else _marker(uid_ref),
    }


def test_shared_folders_empty_manifest_and_live_no_changes() -> None:
    changes = compute_sharing_diff(_manifest(), live_shared_folders=[])

    assert changes == []


def test_shared_folders_manifest_only_adds() -> None:
    changes = compute_sharing_diff(_manifest(_shared_folder()), live_shared_folders=[])

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.ADD
    assert changes[0].uid_ref == "sf.prod"
    assert changes[0].resource_type == "sharing_shared_folder"


def test_shared_folders_live_owned_orphan_deletes_when_allowed() -> None:
    changes = compute_sharing_diff(
        _manifest(),
        live_shared_folders=[_live_shared_folder()],
        allow_delete=True,
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.DELETE


def test_shared_folders_live_owned_orphan_skips_without_allow_delete() -> None:
    changes = compute_sharing_diff(_manifest(), live_shared_folders=[_live_shared_folder()])

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.SKIP
    assert changes[0].reason == "managed shared_folder missing from manifest"


def test_shared_folders_same_fields_no_changes() -> None:
    changes = compute_sharing_diff(
        _manifest(
            _shared_folder(
                defaults={
                    "manage_records": True,
                    "manage_users": False,
                    "can_edit": True,
                    "can_share": False,
                }
            )
        ),
        live_shared_folders=[_live_shared_folder()],
    )

    assert changes == []


def test_shared_folders_name_drift_updates() -> None:
    changes = compute_sharing_diff(
        _manifest(_shared_folder(path="/Shared/Prod New")),
        live_shared_folders=[_live_shared_folder(name="/Shared/Prod")],
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.UPDATE
    assert changes[0].before == {"name": "/Shared/Prod"}
    assert changes[0].after == {"name": "/Shared/Prod New"}


@pytest.mark.parametrize(
    ("field", "manifest_value", "live_value"),
    [
        ("manage_records", False, True),
        ("manage_users", True, False),
        ("can_edit", False, True),
        ("can_share", True, False),
    ],
)
def test_shared_folders_default_field_drift_updates(
    field: str,
    manifest_value: bool,
    live_value: bool,
) -> None:
    defaults = {
        "manage_records": True,
        "manage_users": False,
        "can_edit": True,
        "can_share": False,
    }
    defaults[field] = manifest_value
    live_field = f"default_{field}"
    live = _live_shared_folder()
    live[live_field] = live_value

    changes = compute_sharing_diff(
        _manifest(_shared_folder(defaults=defaults)),
        live_shared_folders=[live],
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.UPDATE
    assert changes[0].before == {live_field: live_value}
    assert changes[0].after == {live_field: manifest_value}


def test_shared_folders_live_unmanaged_skips() -> None:
    changes = compute_sharing_diff(
        _manifest(_shared_folder()),
        live_shared_folders=[_live_shared_folder(marker=_marker(manager="other-manager"))],
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.SKIP
    assert changes[0].reason == "unmanaged shared_folder"


def test_shared_folders_duplicate_manifest_uid_ref_raises() -> None:
    manifest = _manifest(_shared_folder(path="/One"), _shared_folder(path="/Two"))

    with pytest.raises(ValueError, match="duplicate manifest shared_folder uid_ref"):
        compute_sharing_diff(manifest, live_shared_folders=[])


def test_shared_folders_manifest_name_propagates_to_change_rows() -> None:
    changes = compute_sharing_diff(
        _manifest(_shared_folder()),
        live_shared_folders=[],
        manifest_name="customer-prod",
    )

    assert len(changes) == 1
    assert changes[0].manifest_name == "customer-prod"
    assert changes[0].after["marker"]["manifest"] == "customer-prod"


def test_shared_folders_marker_version_mismatch_raises() -> None:
    with pytest.raises(OwnershipError, match="marker version 9999"):
        compute_sharing_diff(
            _manifest(),
            live_shared_folders=[_live_shared_folder(marker=_marker(version="9999"))],
        )


def test_shared_folders_only_diffed_when_live_shared_folders_passed() -> None:
    changes = compute_sharing_diff(
        _manifest(_shared_folder(), folders=[_folder()]),
        live_shared_folders=[],
    )

    assert len(changes) == 1
    assert changes[0].resource_type == "sharing_shared_folder"
