"""Typed models for ``keeper-vault-sharing.v1`` manifests.

Mirrors ``keeper_sdk/core/schemas/keeper-vault-sharing/keeper-vault-sharing.v1.schema.json``.
This first typed slice covers all four top-level blocks; provider apply support
and non-folder diff blocks land in later slices.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from keeper_sdk.core.errors import SchemaError

SHARING_FAMILY: Literal["keeper-vault-sharing.v1"] = "keeper-vault-sharing.v1"

UidRef: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
RecordRef: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^keeper-vault:records:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
TeamRef: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^keeper-enterprise:teams:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
SharingRef: TypeAlias = Annotated[
    str,
    StringConstraints(
        pattern=r"^keeper-vault-sharing:(folders|shared_folders):"
        r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
    ),
]
NonEmptyString: TypeAlias = Annotated[str, StringConstraints(min_length=1)]
FolderColor: TypeAlias = Literal["red", "green", "blue", "orange", "yellow", "gray"]

_SHARING_REF_RE = re.compile(
    r"^keeper-vault-sharing:(?P<block>folders|shared_folders):(?P<uid_ref>.+)$"
)
_RECORD_REF_RE = re.compile(r"^keeper-vault:records:(?P<uid_ref>.+)$")


class _SharingModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class RecordPermissions(_SharingModel):
    """``$defs.record_permissions``."""

    can_edit: bool
    can_share: bool


class FolderGranteePermissions(_SharingModel):
    """``$defs.folder_grantee_permissions``."""

    manage_records: bool
    manage_users: bool


class UserGrantee(_SharingModel):
    """``$defs.grantee`` user branch."""

    kind: Literal["user"]
    user_email: str


class TeamGrantee(_SharingModel):
    """``$defs.grantee`` team branch."""

    kind: Literal["team"]
    team_uid_ref: TeamRef


Grantee: TypeAlias = Annotated[UserGrantee | TeamGrantee, Field(discriminator="kind")]


class SharingFolder(_SharingModel):
    """One ``folders[]`` entry (schema ``$defs.folder``)."""

    uid_ref: UidRef
    path: NonEmptyString
    parent_folder_uid_ref: SharingRef | None = None
    color: FolderColor | None = None


class SharedFolderDefaults(_SharingModel):
    """Optional defaults object on ``shared_folders[]`` entries."""

    manage_users: bool | None = None
    manage_records: bool | None = None
    can_edit: bool | None = None
    can_share: bool | None = None


class SharingSharedFolder(_SharingModel):
    """One ``shared_folders[]`` entry (schema ``$defs.shared_folder``)."""

    uid_ref: UidRef
    path: NonEmptyString
    defaults: SharedFolderDefaults | None = None


class SharingRecordShare(_SharingModel):
    """One ``share_records[]`` entry (schema ``$defs.record_share``)."""

    uid_ref: UidRef
    record_uid_ref: RecordRef
    user_email: str
    permissions: RecordPermissions
    expires_at: str | None = None


class SharedFolderGranteeShare(_SharingModel):
    """``share_folders[]`` grantee branch."""

    kind: Literal["grantee"]
    uid_ref: UidRef
    shared_folder_uid_ref: SharingRef
    grantee: Grantee
    permissions: FolderGranteePermissions
    expires_at: str | None = None


class SharedFolderRecordShare(_SharingModel):
    """``share_folders[]`` record branch."""

    kind: Literal["record"]
    uid_ref: UidRef
    shared_folder_uid_ref: SharingRef
    record_uid_ref: RecordRef
    permissions: RecordPermissions
    expires_at: str | None = None


class SharedFolderDefaultShare(_SharingModel):
    """``share_folders[]`` default-permission branch."""

    kind: Literal["default"]
    uid_ref: UidRef
    shared_folder_uid_ref: SharingRef
    target: Literal["grantee", "record"]
    permissions: FolderGranteePermissions | RecordPermissions


SharingShareFolder: TypeAlias = Annotated[
    SharedFolderGranteeShare | SharedFolderRecordShare | SharedFolderDefaultShare,
    Field(discriminator="kind"),
]


class SharingManifestV1(_SharingModel):
    """Top-level ``keeper-vault-sharing.v1`` manifest.

    ``record_uid_ref`` follows schema ``$defs.record_ref``:
    ``keeper-vault:records:<uid_ref>``. ``parent_folder_uid_ref`` follows
    schema ``$defs.sharing_ref``:
    ``keeper-vault-sharing:(folders|shared_folders):<uid_ref>``. Local matches
    are accepted; absent fully-qualified references are treated as documented
    external references so this sharing manifest can point at existing tenant
    objects or objects declared by another family slice.
    """

    vault_schema: Literal["keeper-vault-sharing.v1"] = Field(
        default=SHARING_FAMILY,
        alias="schema",
    )
    folders: list[SharingFolder] = Field(default_factory=list)
    shared_folders: list[SharingSharedFolder] = Field(default_factory=list)
    share_records: list[SharingRecordShare] = Field(default_factory=list)
    share_folders: list[SharingShareFolder] = Field(default_factory=list)

    @model_validator(mode="after")
    def _references_follow_documented_conventions(self) -> SharingManifestV1:
        known_sharing_refs = {
            f"keeper-vault-sharing:folders:{folder.uid_ref}" for folder in self.folders
        }
        known_sharing_refs.update(
            f"keeper-vault-sharing:shared_folders:{folder.uid_ref}"
            for folder in self.shared_folders
        )

        for folder in self.folders:
            ref = folder.parent_folder_uid_ref
            if ref is None:
                continue
            if ref in known_sharing_refs:
                continue
            if not _SHARING_REF_RE.match(ref):
                raise ValueError(
                    "parent_folder_uid_ref must match "
                    "keeper-vault-sharing:(folders|shared_folders):<uid_ref>"
                )

        for record_share in self.share_records:
            if not _RECORD_REF_RE.match(record_share.record_uid_ref):
                raise ValueError("record_uid_ref must match keeper-vault:records:<uid_ref>")

        for folder_share in self.share_folders:
            if isinstance(folder_share, SharedFolderRecordShare) and not _RECORD_REF_RE.match(
                folder_share.record_uid_ref
            ):
                raise ValueError("record_uid_ref must match keeper-vault:records:<uid_ref>")
        return self


def load_sharing_manifest(document: dict[str, Any]) -> SharingManifestV1:
    """Validate with JSON Schema + semantic rules, then parse as ``SharingManifestV1``."""

    from keeper_sdk.core.schema import SHARING_FAMILY as SCHEMA_SHARING_FAMILY
    from keeper_sdk.core.schema import validate_manifest

    family = validate_manifest(document)
    if family != SCHEMA_SHARING_FAMILY:
        raise SchemaError(
            reason=f"expected {SCHEMA_SHARING_FAMILY!r}, got {family!r}",
            next_action="set schema: keeper-vault-sharing.v1 on the manifest",
        )
    try:
        return SharingManifestV1.model_validate(document)
    except ValueError as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-vault-sharing.v1 typed rules",
        ) from exc
