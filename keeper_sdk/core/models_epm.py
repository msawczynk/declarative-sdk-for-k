"""Typed models for ``keeper-epm.v1`` manifests.

W18 ships an offline foundation only: schema validation, typed load, and
field-level diff. Apply remains an upstream gap until a PEDM tenant writer and
readback path are proven through an MSP managed company.
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

EPM_FAMILY: Literal["keeper-epm.v1"] = "keeper-epm.v1"

UidRef: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
NonEmptyString: TypeAlias = Annotated[str, StringConstraints(min_length=1)]
EmailString: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=3, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
]


class _EpmModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)


class EpmWatchlist(_EpmModel):
    """One EPM allowlist/blocklist row."""

    uid_ref: UidRef
    name: NonEmptyString
    description: str = ""
    policy_type: Literal["allowlist", "blocklist"]
    entries: list[NonEmptyString] = Field(default_factory=list)


class EpmPolicy(_EpmModel):
    """One EPM elevation policy row."""

    uid_ref: UidRef
    name: NonEmptyString
    elevation_type: Literal["auto", "approval", "denied"]
    target_users: list[NonEmptyString] = Field(default_factory=list)
    target_groups: list[NonEmptyString] = Field(default_factory=list)
    application_patterns: list[NonEmptyString] = Field(default_factory=list)


class EpmApprover(_EpmModel):
    """One EPM approver row."""

    uid_ref: UidRef
    name: NonEmptyString
    email: EmailString
    scope_uid_refs: list[UidRef] = Field(default_factory=list)


class EpmAuditConfig(_EpmModel):
    """Tenant-wide EPM audit configuration."""

    retention_days: Annotated[int, Field(ge=1)]
    alert_on_denied: bool
    export_format: Literal["json", "siem", "csv"]


class EpmManifestV1(_EpmModel):
    """Top-level ``keeper-epm.v1`` manifest."""

    epm_schema: Literal["keeper-epm.v1"] = Field(default=EPM_FAMILY, alias="schema")
    watchlists: list[EpmWatchlist] = Field(default_factory=list)
    policies: list[EpmPolicy] = Field(default_factory=list)
    approvers: list[EpmApprover] = Field(default_factory=list)
    audit_config: EpmAuditConfig | None = None

    @model_validator(mode="after")
    def _uid_refs_are_unique(self) -> EpmManifestV1:
        seen: dict[str, str] = {}
        duplicates: set[str] = set()
        for uid_ref, kind in self.iter_uid_refs():
            if uid_ref in seen:
                duplicates.add(uid_ref)
            seen[uid_ref] = kind
        if duplicates:
            raise ValueError(f"duplicate uid_ref values: {sorted(duplicates)}")
        return self

    @model_validator(mode="after")
    def _approver_scopes_exist(self) -> EpmManifestV1:
        policy_refs = {policy.uid_ref for policy in self.policies}
        unknown = sorted(
            {
                scope
                for approver in self.approvers
                for scope in approver.scope_uid_refs
                if scope not in policy_refs
            }
        )
        if unknown:
            raise ValueError(f"approver scope_uid_refs must reference policies: {unknown}")
        return self

    def iter_uid_refs(self) -> list[tuple[str, str]]:
        """Return ``(uid_ref, kind)`` for all EPM objects with manifest handles."""
        refs: list[tuple[str, str]] = []
        refs.extend((row.uid_ref, "epm_watchlist") for row in self.watchlists)
        refs.extend((row.uid_ref, "epm_policy") for row in self.policies)
        refs.extend((row.uid_ref, "epm_approver") for row in self.approvers)
        return refs


def load_epm_manifest(document: dict[str, Any]) -> EpmManifestV1:
    """Validate with JSON Schema, then parse as ``EpmManifestV1``."""
    from keeper_sdk.core.schema import validate_manifest

    family = validate_manifest(document)
    if family != EPM_FAMILY:
        raise SchemaError(
            reason=f"expected {EPM_FAMILY!r}, got {family!r}",
            next_action="set schema: keeper-epm.v1 on the manifest",
        )
    try:
        return EpmManifestV1.model_validate(document)
    except ValidationError as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-epm.v1 typed rules",
        ) from exc
    except (ValueError, TypeError) as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-epm.v1 typed rules",
        ) from exc


__all__ = [
    "EPM_FAMILY",
    "EpmApprover",
    "EpmAuditConfig",
    "EpmManifestV1",
    "EpmPolicy",
    "EpmWatchlist",
    "load_epm_manifest",
]
