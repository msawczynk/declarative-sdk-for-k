"""Offline shared-folder model skeleton tests."""

from __future__ import annotations

from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.vault_models import VaultSharedFolder, diff_shared_folder


def _shared_folder(*, members: list[dict[str, str]] | None = None) -> VaultSharedFolder:
    return VaultSharedFolder.model_validate(
        {
            "title": "Ops Shared",
            "uid_ref": "sf.ops",
            "manager": "keeper-pam-declarative",
            "members": members
            if members is not None
            else [{"email": "alice@example.com", "role": "manage"}],
            "permissions": {"manage_records": True, "manage_users": False},
        }
    )


def test_build_shared_folder_from_dict_fields_correct() -> None:
    folder = _shared_folder()

    assert folder.title == "Ops Shared"
    assert folder.uid_ref == "sf.ops"
    assert folder.manager == "keeper-pam-declarative"
    assert folder.members == [{"email": "alice@example.com", "role": "manage"}]
    assert folder.permissions == {"manage_records": True, "manage_users": False}


def test_shared_folder_diff_member_added_update() -> None:
    before = _shared_folder()
    after = _shared_folder(
        members=[
            {"email": "alice@example.com", "role": "manage"},
            {"email": "bob@example.com", "role": "read"},
        ]
    )

    row = diff_shared_folder(before, after)

    assert row.kind is ChangeKind.UPDATE
    assert row.before["members"] == [{"email": "alice@example.com", "role": "manage"}]
    assert row.after["members"] == [
        {"email": "alice@example.com", "role": "manage"},
        {"email": "bob@example.com", "role": "read"},
    ]


def test_shared_folder_diff_member_removed_update() -> None:
    before = _shared_folder(
        members=[
            {"email": "alice@example.com", "role": "manage"},
            {"email": "bob@example.com", "role": "read"},
        ]
    )
    after = _shared_folder()

    row = diff_shared_folder(before, after)

    assert row.kind is ChangeKind.UPDATE
    assert row.before["members"] == [
        {"email": "alice@example.com", "role": "manage"},
        {"email": "bob@example.com", "role": "read"},
    ]
    assert row.after["members"] == [{"email": "alice@example.com", "role": "manage"}]


def test_shared_folder_diff_identical_noop() -> None:
    before = _shared_folder()
    after = _shared_folder()

    row = diff_shared_folder(before, after)

    assert row.kind is ChangeKind.NOOP
