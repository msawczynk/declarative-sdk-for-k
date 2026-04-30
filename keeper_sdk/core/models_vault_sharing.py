"""Compatibility models for ``keeper-vault-sharing.v1`` manifests.

The canonical implementation lives in :mod:`keeper_sdk.core.sharing_models`.
This module preserves the P10 ``models_vault_sharing`` naming while keeping one
typed model source for the family.
"""

from __future__ import annotations

from typing import Any, TypeAlias

from keeper_sdk.core.sharing_models import (
    SHARING_FAMILY,
    FolderGranteePermissions,
    Grantee,
    RecordPermissions,
    SharedFolderDefaultShare,
    SharedFolderGranteeShare,
    SharedFolderRecordShare,
    SharingFolder,
    SharingManifestV1,
    SharingRecordShare,
    SharingSharedFolder,
    SharingShareFolder,
    load_sharing_manifest,
)

VAULT_SHARING_FAMILY = SHARING_FAMILY

VaultSharingManifestV1: TypeAlias = SharingManifestV1
VaultSharingFolder: TypeAlias = SharingFolder
VaultSharingSharedFolder: TypeAlias = SharingSharedFolder
VaultSharingRecordShare: TypeAlias = SharingRecordShare
VaultSharingShareFolder: TypeAlias = SharingShareFolder
VaultSharingSharedFolderGranteeShare: TypeAlias = SharedFolderGranteeShare
VaultSharingSharedFolderRecordShare: TypeAlias = SharedFolderRecordShare
VaultSharingSharedFolderDefaultShare: TypeAlias = SharedFolderDefaultShare


def load_vault_sharing_manifest(document: dict[str, Any]) -> VaultSharingManifestV1:
    """Validate and load a ``keeper-vault-sharing.v1`` manifest."""

    return load_sharing_manifest(document)


__all__ = [
    "FolderGranteePermissions",
    "Grantee",
    "RecordPermissions",
    "SHARING_FAMILY",
    "VAULT_SHARING_FAMILY",
    "VaultSharingFolder",
    "VaultSharingManifestV1",
    "VaultSharingRecordShare",
    "VaultSharingShareFolder",
    "VaultSharingSharedFolder",
    "VaultSharingSharedFolderDefaultShare",
    "VaultSharingSharedFolderGranteeShare",
    "VaultSharingSharedFolderRecordShare",
    "load_vault_sharing_manifest",
]
