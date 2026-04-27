"""keeper-vault-sharing.v1 folder diff tests."""

from __future__ import annotations

import pytest

from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.core.sharing_diff import compute_sharing_diff
from keeper_sdk.core.sharing_models import SHARING_FAMILY, SharingManifestV1


def _folder(
    uid_ref: str = "folder.prod",
    path: str = "/Prod",
    *,
    parent_folder_uid_ref: str | None = None,
    color: str | None = "blue",
) -> dict[str, str]:
    data = {"uid_ref": uid_ref, "path": path}
    if parent_folder_uid_ref is not None:
        data["parent_folder_uid_ref"] = parent_folder_uid_ref
    if color is not None:
        data["color"] = color
    return data


def _manifest(*folders: dict[str, str]) -> SharingManifestV1:
    return SharingManifestV1.model_validate({"schema": SHARING_FAMILY, "folders": list(folders)})


def _marker(
    uid_ref: str = "folder.prod",
    *,
    manifest_name: str = "vault-sharing",
    manager: str | None = None,
) -> dict[str, object]:
    marker = encode_marker(
        uid_ref=uid_ref,
        manifest=manifest_name,
        resource_type="sharing_folder",
    )
    if manager is not None:
        marker["manager"] = manager
    return marker


def _live_folder(
    uid_ref: str = "folder.prod",
    path: str = "/Prod",
    *,
    parent_folder_uid_ref: str | None = None,
    color: str | None = "blue",
    marker: dict[str, object] | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "keeper_uid": f"live-{uid_ref}",
        "uid_ref": uid_ref,
        "path": path,
    }
    if parent_folder_uid_ref is not None:
        data["parent_folder_uid_ref"] = parent_folder_uid_ref
    if color is not None:
        data["color"] = color
    if marker is not None:
        data["marker"] = marker
    else:
        data["marker"] = _marker(uid_ref)
    return data


def test_sharing_folders_empty_manifest_and_live_no_changes() -> None:
    changes = compute_sharing_diff(_manifest(), live_folders=[])

    assert changes == []


def test_sharing_folders_manifest_only_adds() -> None:
    changes = compute_sharing_diff(_manifest(_folder()), live_folders=[])

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.ADD
    assert changes[0].uid_ref == "folder.prod"
    assert changes[0].resource_type == "sharing_folder"


def test_sharing_folders_live_owned_orphan_deletes_when_allowed() -> None:
    changes = compute_sharing_diff(
        _manifest(),
        live_folders=[_live_folder()],
        allow_delete=True,
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.DELETE


def test_sharing_folders_live_owned_orphan_skips_without_allow_delete() -> None:
    changes = compute_sharing_diff(_manifest(), live_folders=[_live_folder()])

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.SKIP
    assert (
        changes[0].reason == "managed folder missing from manifest; pass --allow-delete to remove"
    )


def test_sharing_folders_same_fields_no_changes() -> None:
    changes = compute_sharing_diff(_manifest(_folder()), live_folders=[_live_folder()])

    assert changes == []


def test_sharing_folders_path_drift_updates() -> None:
    changes = compute_sharing_diff(
        _manifest(_folder(path="/Prod/New")),
        live_folders=[_live_folder(path="/Prod")],
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.UPDATE
    assert changes[0].before == {"path": "/Prod"}
    assert changes[0].after == {"path": "/Prod/New"}


def test_sharing_folders_parent_folder_uid_ref_drift_updates() -> None:
    changes = compute_sharing_diff(
        _manifest(
            _folder(
                parent_folder_uid_ref="keeper-vault-sharing:folders:folder.new-parent",
            )
        ),
        live_folders=[
            _live_folder(
                parent_folder_uid_ref="keeper-vault-sharing:folders:folder.old-parent",
            )
        ],
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.UPDATE
    assert changes[0].before == {
        "parent_folder_uid_ref": "keeper-vault-sharing:folders:folder.old-parent"
    }
    assert changes[0].after == {
        "parent_folder_uid_ref": "keeper-vault-sharing:folders:folder.new-parent"
    }


def test_sharing_folders_color_drift_updates() -> None:
    changes = compute_sharing_diff(
        _manifest(_folder(color="green")),
        live_folders=[_live_folder(color="blue")],
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.UPDATE
    assert changes[0].before == {"color": "blue"}
    assert changes[0].after == {"color": "green"}


def test_sharing_folders_live_unmanaged_skips() -> None:
    changes = compute_sharing_diff(
        _manifest(_folder()),
        live_folders=[_live_folder(marker=_marker(manager="other-manager"))],
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.SKIP
    assert changes[0].reason == "unmanaged folder"


def test_sharing_folders_duplicate_manifest_uid_ref_raises() -> None:
    manifest = _manifest(_folder(path="/Prod"), _folder(path="/Prod 2"))

    with pytest.raises(ValueError, match="duplicate manifest folder uid_ref"):
        compute_sharing_diff(manifest, live_folders=[])


def test_compute_sharing_diff_empty_future_block_has_no_changes() -> None:
    changes = compute_sharing_diff(_manifest(), live_shared_folders=[])

    assert changes == []


def test_sharing_folders_manifest_name_propagates_to_change_rows() -> None:
    changes = compute_sharing_diff(
        _manifest(_folder()),
        live_folders=[],
        manifest_name="customer-prod",
    )

    assert len(changes) == 1
    assert changes[0].manifest_name == "customer-prod"
    assert changes[0].after["marker"]["manifest"] == "customer-prod"
