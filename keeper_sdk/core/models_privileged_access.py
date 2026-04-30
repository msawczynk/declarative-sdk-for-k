"""Typed models for ``keeper-privileged-access.v1`` manifests."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from keeper_sdk.core.errors import SchemaError

PRIVILEGED_ACCESS_FAMILY: Literal["keeper-privileged-access.v1"] = "keeper-privileged-access.v1"

UidRef: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
PrivilegedUserRef: TypeAlias = Annotated[
    str,
    StringConstraints(
        pattern=r"^keeper-privileged-access:users:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
    ),
]
PrivilegedGroupRef: TypeAlias = Annotated[
    str,
    StringConstraints(
        pattern=r"^keeper-privileged-access:groups:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
    ),
]
NonEmptyString: TypeAlias = Annotated[str, StringConstraints(min_length=1)]


class _PrivilegedAccessModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)


class PrivilegedUser(_PrivilegedAccessModel):
    """One privileged cloud-access user target."""

    uid_ref: UidRef
    principal: NonEmptyString
    provider: Literal["aws", "azure", "gcp", "generic"] = "generic"
    enabled: bool = True


class PrivilegedGroup(_PrivilegedAccessModel):
    """One privileged cloud-access group."""

    uid_ref: UidRef
    name: NonEmptyString
    provider: Literal["aws", "azure", "gcp", "generic"] = "generic"
    enabled: bool = True


class PrivilegedGroupMembership(_PrivilegedAccessModel):
    """One user-to-group binding."""

    uid_ref: UidRef
    user_uid_ref: PrivilegedUserRef
    group_uid_ref: PrivilegedGroupRef


class PrivilegedAccessManifestV1(_PrivilegedAccessModel):
    """Top-level ``keeper-privileged-access.v1`` manifest."""

    privileged_access_schema: Literal["keeper-privileged-access.v1"] = Field(
        default=PRIVILEGED_ACCESS_FAMILY,
        alias="schema",
    )
    users: list[PrivilegedUser] = Field(default_factory=list)
    groups: list[PrivilegedGroup] = Field(default_factory=list)
    group_memberships: list[PrivilegedGroupMembership] = Field(default_factory=list)

    @model_validator(mode="after")
    def _refs_are_consistent(self) -> PrivilegedAccessManifestV1:
        seen: dict[str, str] = {}
        duplicates: list[str] = []
        for uid_ref, kind in self.iter_uid_refs():
            if uid_ref in seen:
                duplicates.append(uid_ref)
            seen[uid_ref] = kind
        if duplicates:
            raise ValueError(f"duplicate uid_ref values: {sorted(set(duplicates))}")

        users = {user.uid_ref for user in self.users}
        groups = {group.uid_ref for group in self.groups}
        missing_users = sorted(
            {
                _ref_uid(membership.user_uid_ref)
                for membership in self.group_memberships
                if _ref_uid(membership.user_uid_ref) not in users
            }
        )
        if missing_users:
            raise ValueError(f"unknown privileged user refs: {missing_users}")
        missing_groups = sorted(
            {
                _ref_uid(membership.group_uid_ref)
                for membership in self.group_memberships
                if _ref_uid(membership.group_uid_ref) not in groups
            }
        )
        if missing_groups:
            raise ValueError(f"unknown privileged group refs: {missing_groups}")
        return self

    def iter_uid_refs(self) -> list[tuple[str, str]]:
        refs: list[tuple[str, str]] = []
        refs.extend((user.uid_ref, "privileged_user") for user in self.users)
        refs.extend((group.uid_ref, "privileged_group") for group in self.groups)
        refs.extend(
            (membership.uid_ref, "privileged_group_membership")
            for membership in self.group_memberships
        )
        return refs


def _ref_uid(ref: str) -> str:
    return ref.rsplit(":", 1)[-1]


def load_privileged_access_manifest(document: dict[str, Any]) -> PrivilegedAccessManifestV1:
    """Validate with JSON Schema, then parse as ``PrivilegedAccessManifestV1``."""
    from keeper_sdk.core.schema import validate_manifest

    family = validate_manifest(document)
    if family != PRIVILEGED_ACCESS_FAMILY:
        raise SchemaError(
            reason=f"expected {PRIVILEGED_ACCESS_FAMILY!r}, got {family!r}",
            next_action="set schema: keeper-privileged-access.v1 on the manifest",
        )
    try:
        return PrivilegedAccessManifestV1.model_validate(document)
    except ValidationError as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-privileged-access.v1 typed rules",
        ) from exc
    except (ValueError, TypeError) as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-privileged-access.v1 typed rules",
        ) from exc


__all__ = [
    "PRIVILEGED_ACCESS_FAMILY",
    "PrivilegedAccessManifestV1",
    "PrivilegedGroup",
    "PrivilegedGroupMembership",
    "PrivilegedUser",
    "load_privileged_access_manifest",
]
