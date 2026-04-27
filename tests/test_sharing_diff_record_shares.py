"""keeper-vault-sharing.v1 ``share_records[]`` sibling-block diff tests."""

from __future__ import annotations

import pytest

from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.errors import OwnershipError
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.core.sharing_diff import compute_sharing_diff
from keeper_sdk.core.sharing_models import SHARING_FAMILY, SharingManifestV1


def _record_share(
    uid_ref: str = "share.web.platform",
    record_uid_ref: str = "keeper-vault:records:rec.web",
    user_email: str = "platform@example.com",
    *,
    can_edit: bool = True,
    can_share: bool = False,
    expires_at: str | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "uid_ref": uid_ref,
        "record_uid_ref": record_uid_ref,
        "user_email": user_email,
        "permissions": {"can_edit": can_edit, "can_share": can_share},
    }
    if expires_at is not None:
        data["expires_at"] = expires_at
    return data


def _manifest(*share_records: dict[str, object]) -> SharingManifestV1:
    return SharingManifestV1.model_validate(
        {"schema": SHARING_FAMILY, "share_records": list(share_records)}
    )


def _marker(
    uid_ref: str = "share.web.platform",
    *,
    manifest_name: str = "vault-sharing",
    manager: str | None = None,
    version: str | None = None,
) -> dict[str, object]:
    marker = encode_marker(
        uid_ref=uid_ref,
        manifest=manifest_name,
        resource_type="sharing_record_share",
        parent_uid_ref="keeper-vault:records:rec.web",
    )
    if manager is not None:
        marker["manager"] = manager
    if version is not None:
        marker["version"] = version
    return marker


def _live_record_share(
    uid_ref: str = "share.web.platform",
    record_uid_ref: str = "keeper-vault:records:rec.web",
    user_email: str | None = "platform@example.com",
    *,
    grantee: dict[str, str] | None = None,
    can_edit: bool = True,
    can_share: bool = False,
    expires_at: str | None = None,
    marker: dict[str, object] | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "keeper_uid": f"live-{uid_ref}",
        "uid_ref": uid_ref,
        "record_uid_ref": record_uid_ref,
        "permissions": {"can_edit": can_edit, "can_share": can_share},
        "marker": marker if marker is not None else _marker(uid_ref),
    }
    if user_email is not None:
        data["user_email"] = user_email
    if grantee is not None:
        data["grantee"] = grantee
    if expires_at is not None:
        data["expires_at"] = expires_at
    return data


def test_record_shares_empty_manifest_and_live_no_changes() -> None:
    changes = compute_sharing_diff(_manifest(), live_share_records=[])

    assert changes == []


def test_record_shares_manifest_only_adds() -> None:
    changes = compute_sharing_diff(_manifest(_record_share()), live_share_records=[])

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.ADD
    assert changes[0].uid_ref == "share.web.platform"
    assert changes[0].resource_type == "sharing_record_share"


def test_record_shares_live_owned_orphan_deletes_when_allowed() -> None:
    changes = compute_sharing_diff(
        _manifest(),
        live_share_records=[_live_record_share()],
        allow_delete=True,
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.DELETE


def test_record_shares_live_owned_orphan_skips_without_allow_delete() -> None:
    changes = compute_sharing_diff(_manifest(), live_share_records=[_live_record_share()])

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.SKIP
    assert changes[0].reason == "managed record_share missing from manifest"


def test_record_shares_same_fields_no_changes() -> None:
    changes = compute_sharing_diff(
        _manifest(_record_share()),
        live_share_records=[_live_record_share()],
    )

    assert changes == []


@pytest.mark.parametrize(
    ("field", "manifest_value", "live_value"),
    [("can_edit", False, True), ("can_share", True, False)],
)
def test_record_shares_permission_drift_updates(
    field: str,
    manifest_value: bool,
    live_value: bool,
) -> None:
    manifest_can_edit = manifest_value if field == "can_edit" else True
    manifest_can_share = manifest_value if field == "can_share" else False
    live_can_edit = live_value if field == "can_edit" else True
    live_can_share = live_value if field == "can_share" else False

    changes = compute_sharing_diff(
        _manifest(
            _record_share(
                can_edit=manifest_can_edit,
                can_share=manifest_can_share,
            )
        ),
        live_share_records=[
            _live_record_share(
                can_edit=live_can_edit,
                can_share=live_can_share,
            )
        ],
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.UPDATE
    assert changes[0].before == {field: live_value}
    assert changes[0].after == {field: manifest_value}


def test_record_shares_composite_key_matches_when_uid_ref_differs() -> None:
    changes = compute_sharing_diff(
        _manifest(_record_share(uid_ref="share.web.new")),
        live_share_records=[_live_record_share(uid_ref="share.web.old")],
    )

    assert changes == []


def test_record_shares_same_record_different_grantee_adds_two_rows() -> None:
    changes = compute_sharing_diff(
        _manifest(
            _record_share(uid_ref="share.web.a", user_email="a@example.com"),
            _record_share(uid_ref="share.web.b", user_email="b@example.com"),
        ),
        live_share_records=[],
    )

    assert [change.kind for change in changes] == [ChangeKind.ADD, ChangeKind.ADD]
    assert [change.uid_ref for change in changes] == ["share.web.a", "share.web.b"]


def test_record_shares_grantee_type_swap_conflicts() -> None:
    changes = compute_sharing_diff(
        _manifest(_record_share()),
        live_share_records=[
            _live_record_share(
                user_email=None,
                grantee={
                    "kind": "team",
                    "team_uid_ref": "keeper-enterprise:teams:team.ops",
                },
            )
        ],
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.CONFLICT
    assert "record_share grantee changed" in str(changes[0].reason)


def test_record_shares_live_unmanaged_skips() -> None:
    changes = compute_sharing_diff(
        _manifest(_record_share()),
        live_share_records=[_live_record_share(marker=_marker(manager="other-manager"))],
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.SKIP
    assert changes[0].reason == "unmanaged record_share"


def test_record_shares_duplicate_manifest_uid_ref_raises() -> None:
    manifest = _manifest(
        _record_share(record_uid_ref="keeper-vault:records:rec.one"),
        _record_share(record_uid_ref="keeper-vault:records:rec.two"),
    )

    with pytest.raises(ValueError, match="duplicate manifest record_share uid_ref"):
        compute_sharing_diff(manifest, live_share_records=[])


def test_record_shares_manifest_name_propagates_to_change_rows() -> None:
    changes = compute_sharing_diff(
        _manifest(_record_share()),
        live_share_records=[],
        manifest_name="customer-prod",
    )

    assert len(changes) == 1
    assert changes[0].manifest_name == "customer-prod"
    assert changes[0].after["marker"]["manifest"] == "customer-prod"


def test_record_shares_marker_version_mismatch_raises() -> None:
    with pytest.raises(OwnershipError, match="marker version 9999"):
        compute_sharing_diff(
            _manifest(),
            live_share_records=[_live_record_share(marker=_marker(version="9999"))],
        )
