"""Typed models for ``keeper-integrations-identity.v1`` manifests.

W14 ships an offline foundation only: schema validation, typed load, and
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

IDENTITY_FAMILY: Literal["keeper-integrations-identity.v1"] = "keeper-integrations-identity.v1"

UidRef: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
RecordRef: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^keeper-vault:records:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
RoleRef: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^keeper-enterprise:roles:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
DomainName: TypeAlias = Annotated[
    str,
    StringConstraints(
        min_length=3,
        pattern=(
            r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
            r"(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
        ),
    ),
]
NonEmptyString: TypeAlias = Annotated[str, StringConstraints(min_length=1)]
EmailString: TypeAlias = Annotated[str, StringConstraints(min_length=3)]


class _IdentityModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)


class IdentityDomain(_IdentityModel):
    """One verified domain row."""

    name: DomainName
    verified: bool = False
    primary: bool = False


class IdentityScimProvisioning(_IdentityModel):
    """One SCIM provisioning configuration."""

    name: NonEmptyString
    uid_ref: UidRef
    provider: Literal["okta", "azure", "google", "generic"]
    sync_groups: bool = False
    base_url: NonEmptyString
    token_uid_ref: RecordRef


class IdentitySsoProvider(_IdentityModel):
    """One SSO provider configuration."""

    name: NonEmptyString
    uid_ref: UidRef
    type: Literal["saml", "oidc"]
    entity_id: NonEmptyString
    metadata_url: NonEmptyString
    default_role_uid_ref: RoleRef | None = None


class IdentityOutboundEmail(_IdentityModel):
    """Outbound email sender configuration."""

    from_address: EmailString
    reply_to: EmailString
    smtp_uid_ref: RecordRef | None = None


class IdentityManifestV1(_IdentityModel):
    """Top-level ``keeper-integrations-identity.v1`` manifest."""

    identity_schema: Literal["keeper-integrations-identity.v1"] = Field(
        default=IDENTITY_FAMILY,
        alias="schema",
    )
    domains: list[IdentityDomain] = Field(default_factory=list)
    scim: list[IdentityScimProvisioning] = Field(default_factory=list)
    sso_providers: list[IdentitySsoProvider] = Field(default_factory=list)
    outbound_email: IdentityOutboundEmail | None = None

    @model_validator(mode="after")
    def _refs_are_unique(self) -> IdentityManifestV1:
        seen_uid_refs: dict[str, str] = {}
        dup_uid_refs: list[str] = []
        for uid_ref, kind in self.iter_uid_refs():
            if uid_ref in seen_uid_refs:
                dup_uid_refs.append(uid_ref)
            seen_uid_refs[uid_ref] = kind
        if dup_uid_refs:
            raise ValueError(f"duplicate uid_ref values: {sorted(set(dup_uid_refs))}")

        seen_domains: dict[str, str] = {}
        dup_domains: list[str] = []
        for domain in self.domains:
            key = domain.name.casefold()
            if key in seen_domains:
                dup_domains.append(domain.name)
            seen_domains[key] = domain.name
        if dup_domains:
            raise ValueError(
                f"duplicate domain names case-insensitively: {sorted(set(dup_domains))}"
            )
        return self

    def iter_uid_refs(self) -> list[tuple[str, str]]:
        """Return ``(uid_ref, kind)`` for SCIM and SSO objects."""
        refs: list[tuple[str, str]] = []
        refs.extend((row.uid_ref, "identity_scim") for row in self.scim)
        refs.extend((row.uid_ref, "identity_sso_provider") for row in self.sso_providers)
        return refs


def load_identity_manifest(document: dict[str, Any]) -> IdentityManifestV1:
    """Validate with JSON Schema + semantic rules, then parse as ``IdentityManifestV1``."""
    from keeper_sdk.core.schema import validate_manifest

    family = validate_manifest(document)
    if family != IDENTITY_FAMILY:
        raise SchemaError(
            reason=f"expected {IDENTITY_FAMILY!r}, got {family!r}",
            next_action="set schema: keeper-integrations-identity.v1 on the manifest",
        )
    try:
        return IdentityManifestV1.model_validate(document)
    except ValidationError as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-integrations-identity.v1 typed rules",
        ) from exc
    except (ValueError, TypeError) as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-integrations-identity.v1 typed rules",
        ) from exc


__all__ = [
    "IDENTITY_FAMILY",
    "IdentityDomain",
    "IdentityManifestV1",
    "IdentityOutboundEmail",
    "IdentityScimProvisioning",
    "IdentitySsoProvider",
    "load_identity_manifest",
]
