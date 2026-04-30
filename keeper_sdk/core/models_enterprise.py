"""Typed models for ``keeper-enterprise.v1`` manifests.

P11 ships an offline foundation only: schema validation, typed load, graph, and
field-level diff. Commander online validate / apply remain future slices.
"""

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

ENTERPRISE_FAMILY: Literal["keeper-enterprise.v1"] = "keeper-enterprise.v1"

UidRef: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
NodeRef: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^keeper-enterprise:nodes:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
UserRef: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^keeper-enterprise:users:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
RoleRef: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^keeper-enterprise:roles:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
NonEmptyString: TypeAlias = Annotated[str, StringConstraints(min_length=1)]


class _EnterpriseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)


class Node(_EnterpriseModel):
    """One enterprise node."""

    uid_ref: UidRef
    name: NonEmptyString
    parent_uid_ref: NodeRef | None = None


class EnterpriseUser(_EnterpriseModel):
    """One enterprise user row."""

    uid_ref: UidRef
    email: NonEmptyString
    name: NonEmptyString | None = None
    node_uid_ref: NodeRef | None = None
    status: Literal["active", "invited", "disabled", "locked"] = "active"
    lock_status: Literal["locked", "unlocked"] | None = None
    pending_approval: bool | None = None


class Role(_EnterpriseModel):
    """One enterprise role row plus user assignments owned by that role."""

    uid_ref: UidRef
    name: NonEmptyString
    node_uid_ref: NodeRef
    user_uid_refs: list[UserRef] = Field(default_factory=list)
    visible_below: bool | None = None
    new_user_inherit: bool | None = None
    manage_nodes: bool | None = None


class Team(_EnterpriseModel):
    """One enterprise team row plus direct users and role links."""

    uid_ref: UidRef
    name: NonEmptyString
    node_uid_ref: NodeRef
    user_uid_refs: list[UserRef] = Field(default_factory=list)
    role_uid_refs: list[RoleRef] = Field(default_factory=list)
    restrict_edit: bool | None = None
    restrict_share: bool | None = None
    restrict_view: bool | None = None


class Enforcement(_EnterpriseModel):
    """One role enforcement setting."""

    uid_ref: UidRef
    role_uid_ref: RoleRef
    key: NonEmptyString
    value: Any


class Alias(_EnterpriseModel):
    """One secondary email alias for an enterprise user."""

    uid_ref: UidRef
    user_uid_ref: UserRef
    email: NonEmptyString


class EnterpriseManifestV1(_EnterpriseModel):
    """Top-level ``keeper-enterprise.v1`` manifest."""

    enterprise_schema: Literal["keeper-enterprise.v1"] = Field(
        default=ENTERPRISE_FAMILY,
        alias="schema",
    )
    nodes: list[Node] = Field(default_factory=list)
    users: list[EnterpriseUser] = Field(default_factory=list)
    roles: list[Role] = Field(default_factory=list)
    teams: list[Team] = Field(default_factory=list)
    enforcements: list[Enforcement] = Field(default_factory=list)
    aliases: list[Alias] = Field(default_factory=list)

    @model_validator(mode="after")
    def _uid_refs_are_unique(self) -> EnterpriseManifestV1:
        seen: dict[str, str] = {}
        dup: list[str] = []
        for uid_ref, kind in self.iter_uid_refs():
            if uid_ref in seen:
                dup.append(uid_ref)
            seen[uid_ref] = kind
        if dup:
            raise ValueError(f"duplicate uid_ref values: {sorted(set(dup))}")
        return self

    def iter_uid_refs(self) -> list[tuple[str, str]]:
        """Return ``(uid_ref, kind)`` for every enterprise object."""
        refs: list[tuple[str, str]] = []
        refs.extend((row.uid_ref, "enterprise_node") for row in self.nodes)
        refs.extend((row.uid_ref, "enterprise_user") for row in self.users)
        refs.extend((row.uid_ref, "enterprise_role") for row in self.roles)
        refs.extend((row.uid_ref, "enterprise_team") for row in self.teams)
        refs.extend((row.uid_ref, "enterprise_enforcement") for row in self.enforcements)
        refs.extend((row.uid_ref, "enterprise_alias") for row in self.aliases)
        return refs


def load_enterprise_manifest(document: dict[str, Any]) -> EnterpriseManifestV1:
    """Validate with JSON Schema + semantic rules, then parse as ``EnterpriseManifestV1``."""
    from keeper_sdk.core.schema import validate_manifest

    family = validate_manifest(document)
    if family != ENTERPRISE_FAMILY:
        raise SchemaError(
            reason=f"expected {ENTERPRISE_FAMILY!r}, got {family!r}",
            next_action="set schema: keeper-enterprise.v1 on the manifest",
        )
    try:
        return EnterpriseManifestV1.model_validate(document)
    except ValidationError as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-enterprise.v1 typed rules",
        ) from exc
    except (ValueError, TypeError) as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-enterprise.v1 typed rules",
        ) from exc


__all__ = [
    "ENTERPRISE_FAMILY",
    "Alias",
    "Enforcement",
    "EnterpriseManifestV1",
    "EnterpriseUser",
    "Node",
    "Role",
    "Team",
    "load_enterprise_manifest",
]
