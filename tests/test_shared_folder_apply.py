"""Vault shared-folder MockProvider apply tests."""

from __future__ import annotations

from typing import Any

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.interfaces import ApplyOutcome, LiveRecord
from keeper_sdk.core.metadata import (
    MANAGER_NAME,
    MARKER_FIELD_LABEL,
    encode_marker,
    serialize_marker,
)
from keeper_sdk.core.planner import build_plan
from keeper_sdk.core.vault_diff import compute_vault_diff
from keeper_sdk.core.vault_models import (
    VaultManifestV1,
    VaultSharedFolder,
    diff_shared_folder,
)
from keeper_sdk.providers import MockProvider

MANIFEST_NAME = "vault-shared-folder"
RESOURCE_TYPE = "shared_folder"


def _members(*emails_and_roles: tuple[str, str]) -> list[dict[str, str]]:
    return [{"email": email, "role": role} for email, role in emails_and_roles]


def _shared_folder(
    *,
    members: list[dict[str, str]] | None = None,
) -> VaultSharedFolder:
    return VaultSharedFolder.model_validate(
        {
            "title": "Ops Shared",
            "uid_ref": "sf.ops",
            "manager": MANAGER_NAME,
            "members": members
            if members is not None
            else _members(("alice@example.com", "manage")),
            "permissions": {"manage_records": True, "manage_users": False},
        }
    )


def _payload(folder: VaultSharedFolder) -> dict[str, Any]:
    return folder.model_dump(mode="python")


def _create_change(folder: VaultSharedFolder) -> Change:
    return Change(
        kind=ChangeKind.CREATE,
        uid_ref=folder.uid_ref,
        resource_type=RESOURCE_TYPE,
        title=folder.title,
        after=_payload(folder),
    )


def _seed_shared_folder(provider: MockProvider, folder: VaultSharedFolder) -> str:
    marker = encode_marker(
        uid_ref=folder.uid_ref,
        manifest=MANIFEST_NAME,
        resource_type=RESOURCE_TYPE,
    )
    payload = _payload(folder)
    payload["custom_fields"] = {MARKER_FIELD_LABEL: serialize_marker(marker)}
    keeper_uid = f"live-{folder.uid_ref}"
    provider.seed(
        [
            LiveRecord(
                keeper_uid=keeper_uid,
                title=folder.title,
                resource_type=RESOURCE_TYPE,
                payload=payload,
                marker=marker,
            )
        ]
    )
    return keeper_uid


def _live_shared_folders(provider: MockProvider) -> list[LiveRecord]:
    return [record for record in provider.discover() if record.resource_type == RESOURCE_TYPE]


def _apply(provider: MockProvider, changes: list[Change]) -> list[ApplyOutcome]:
    return provider.apply_plan(
        build_plan(
            MANIFEST_NAME,
            changes,
            [change.uid_ref for change in changes if change.uid_ref],
        )
    )


def test_mock_provider_apply_creates_shared_folder_success_row() -> None:
    folder = _shared_folder()
    provider = MockProvider(MANIFEST_NAME)

    outcomes = _apply(provider, [_create_change(folder)])
    [record] = _live_shared_folders(provider)

    assert [outcome.action for outcome in outcomes] == ["create"]
    assert outcomes[0].uid_ref == "sf.ops"
    assert record.resource_type == RESOURCE_TYPE
    assert record.payload["members"] == folder.members
    assert record.marker is not None
    assert record.marker["uid_ref"] == "sf.ops"


def test_mock_provider_apply_updates_shared_folder_membership() -> None:
    before = _shared_folder()
    after = _shared_folder(
        members=_members(
            ("alice@example.com", "manage"),
            ("bob@example.com", "read"),
        )
    )
    provider = MockProvider(MANIFEST_NAME)
    keeper_uid = _seed_shared_folder(provider, before)
    change = diff_shared_folder(before, after)
    change.keeper_uid = keeper_uid

    outcomes = _apply(provider, [change])
    [record] = _live_shared_folders(provider)

    assert change.kind is ChangeKind.UPDATE
    assert change.after == {"members": after.members}
    assert [outcome.action for outcome in outcomes] == ["update"]
    assert record.payload["members"] == after.members


def test_mock_provider_apply_same_shared_folder_state_is_noop() -> None:
    folder = _shared_folder()
    provider = MockProvider(MANIFEST_NAME)
    keeper_uid = _seed_shared_folder(provider, folder)
    change = diff_shared_folder(folder, folder)
    change.keeper_uid = keeper_uid

    outcomes = _apply(provider, [change])

    assert change.kind is ChangeKind.NOOP
    assert outcomes == []
    assert _live_shared_folders(provider)[0].payload["members"] == folder.members


def test_mock_provider_apply_refuses_shared_folder_delete_without_allow_delete() -> None:
    provider = MockProvider(MANIFEST_NAME)
    _seed_shared_folder(provider, _shared_folder())
    manifest = VaultManifestV1.model_validate({"schema": "keeper-vault.v1"})

    changes = compute_vault_diff(
        manifest,
        provider.discover(),
        manifest_name=MANIFEST_NAME,
        allow_delete=False,
    )
    outcomes = _apply(provider, changes)

    assert [change.kind for change in changes] == [ChangeKind.CONFLICT]
    assert changes[0].resource_type == RESOURCE_TYPE
    assert (
        changes[0].reason == "managed record missing from manifest; pass --allow-delete to remove"
    )
    assert outcomes == []
    assert len(_live_shared_folders(provider)) == 1
