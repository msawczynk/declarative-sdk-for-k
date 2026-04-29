"""Typed models for ``keeper-pam-extended.v1`` manifests.

W17 ships an offline foundation only: schema validation, typed load, and
field-level diff. Commander plan/apply remain preview-gated until live proof.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from keeper_sdk.core.errors import SchemaError

PAM_EXTENDED_FAMILY: Literal["keeper-pam-extended.v1"] = "keeper-pam-extended.v1"

UidRef: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
NonEmptyString: TypeAlias = Annotated[str, StringConstraints(min_length=1)]
EmailString: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=3, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
]
PortNumber: TypeAlias = Annotated[int, Field(ge=1, le=65535)]


class _PamExtendedModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)


class PamExtendedGatewayConfig(_PamExtendedModel):
    """Advanced settings for one existing PAM gateway."""

    gateway_uid_ref: UidRef
    network_segment: NonEmptyString
    allowed_ports: list[PortNumber] = Field(default_factory=list)
    health_check_interval_s: int = Field(ge=1)


class PamExtendedRotationSchedule(_PamExtendedModel):
    """Cron-backed rotation schedule targeting PAM resources."""

    name: NonEmptyString
    uid_ref: UidRef
    cron_expr: NonEmptyString
    resource_uid_refs: list[UidRef] = Field(default_factory=list)
    notify_emails: list[EmailString] = Field(default_factory=list)


class PamExtendedDiscoveryRule(_PamExtendedModel):
    """Network discovery rule for PAM resource adoption."""

    name: NonEmptyString
    uid_ref: UidRef
    scan_network: NonEmptyString
    target_cidr: NonEmptyString
    protocol: Literal["ssh", "rdp", "database"]
    credential_uid_ref: UidRef


class PamExtendedServiceMapping(_PamExtendedModel):
    """Service-to-host credential mapping."""

    name: NonEmptyString
    uid_ref: UidRef
    service_type: Literal["windows_service", "unix_daemon", "k8s_pod"]
    host_uid_ref: UidRef
    credential_uid_ref: UidRef


class PamExtendedManifestV1(_PamExtendedModel):
    """Top-level ``keeper-pam-extended.v1`` manifest."""

    pam_extended_schema: Literal["keeper-pam-extended.v1"] = Field(
        default=PAM_EXTENDED_FAMILY,
        alias="schema",
    )
    name: NonEmptyString
    manager: NonEmptyString | None = None
    gateway_configs: list[PamExtendedGatewayConfig] = Field(default_factory=list)
    rotation_schedules: list[PamExtendedRotationSchedule] = Field(default_factory=list)
    discovery_rules: list[PamExtendedDiscoveryRule] = Field(default_factory=list)
    service_mappings: list[PamExtendedServiceMapping] = Field(default_factory=list)

    @field_validator(
        "gateway_configs",
        "rotation_schedules",
        "discovery_rules",
        "service_mappings",
    )
    @classmethod
    def _collections_non_null(cls, value: list[Any]) -> list[Any]:
        return value

    @model_validator(mode="after")
    def _refs_are_unique(self) -> PamExtendedManifestV1:
        seen_uid_refs: dict[str, str] = {}
        dup_uid_refs: list[str] = []
        for uid_ref, kind in self.iter_uid_refs():
            if uid_ref in seen_uid_refs:
                dup_uid_refs.append(uid_ref)
            seen_uid_refs[uid_ref] = kind
        if dup_uid_refs:
            raise ValueError(f"duplicate uid_ref values: {sorted(set(dup_uid_refs))}")

        seen_gateways: set[str] = set()
        dup_gateways: list[str] = []
        for row in self.gateway_configs:
            if row.gateway_uid_ref in seen_gateways:
                dup_gateways.append(row.gateway_uid_ref)
            seen_gateways.add(row.gateway_uid_ref)
        if dup_gateways:
            raise ValueError(
                f"duplicate gateway_uid_ref values: {sorted(set(dup_gateways))}"
            )
        return self

    def iter_uid_refs(self) -> list[tuple[str, str]]:
        """Return ``(uid_ref, kind)`` for objects keyed by uid_ref."""
        refs: list[tuple[str, str]] = []
        refs.extend((row.uid_ref, "pam_extended_rotation_schedule") for row in self.rotation_schedules)
        refs.extend((row.uid_ref, "pam_extended_discovery_rule") for row in self.discovery_rules)
        refs.extend((row.uid_ref, "pam_extended_service_mapping") for row in self.service_mappings)
        return refs


def load_pam_extended_manifest(document: dict[str, Any]) -> PamExtendedManifestV1:
    """Validate with JSON Schema + semantic rules, then parse typed model."""
    from keeper_sdk.core.schema import validate_manifest

    family = validate_manifest(document)
    if family != PAM_EXTENDED_FAMILY:
        raise SchemaError(
            reason=f"expected {PAM_EXTENDED_FAMILY!r}, got {family!r}",
            next_action="set schema: keeper-pam-extended.v1 on the manifest",
        )
    try:
        return PamExtendedManifestV1.model_validate(document)
    except ValidationError as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-pam-extended.v1 typed rules",
        ) from exc
    except (ValueError, TypeError) as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-pam-extended.v1 typed rules",
        ) from exc


__all__ = [
    "PAM_EXTENDED_FAMILY",
    "PamExtendedDiscoveryRule",
    "PamExtendedGatewayConfig",
    "PamExtendedManifestV1",
    "PamExtendedRotationSchedule",
    "PamExtendedServiceMapping",
    "load_pam_extended_manifest",
]
