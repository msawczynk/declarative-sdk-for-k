"""Typed models for ``keeper-pam-extended.v1`` manifests.

W17 ships an offline foundation only: schema validation, typed load, and
field-level diff. Commander plan/apply remain preview-gated until live proof.
"""

from __future__ import annotations

from collections.abc import Iterable
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
    """One advanced gateway configuration row."""

    gateway_uid_ref: UidRef
    network_segment: NonEmptyString
    allowed_ports: list[PortNumber] = Field(default_factory=list)
    health_check_interval_s: Annotated[int, Field(ge=1)]


class PamExtendedRotationSchedule(_PamExtendedModel):
    """One named PAM rotation schedule."""

    name: NonEmptyString
    uid_ref: UidRef
    cron_expr: Annotated[str, StringConstraints(min_length=5)]
    resource_uid_refs: list[UidRef] = Field(default_factory=list)
    notify_emails: list[EmailString] = Field(default_factory=list)


class PamExtendedDiscoveryRule(_PamExtendedModel):
    """One discovery rule for unmanaged PAM targets."""

    name: NonEmptyString
    uid_ref: UidRef
    scan_network: NonEmptyString | bool
    target_cidr: NonEmptyString
    protocol: Literal["ssh", "rdp", "database"]
    credential_uid_ref: UidRef


class PamExtendedServiceMapping(_PamExtendedModel):
    """One service-to-credential mapping."""

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
    gateway_configs: list[PamExtendedGatewayConfig] = Field(default_factory=list)
    rotation_schedules: list[PamExtendedRotationSchedule] = Field(default_factory=list)
    discovery_rules: list[PamExtendedDiscoveryRule] = Field(default_factory=list)
    service_mappings: list[PamExtendedServiceMapping] = Field(default_factory=list)

    @model_validator(mode="after")
    def _object_refs_are_unique(self) -> PamExtendedManifestV1:
        duplicate_gateway_refs = _duplicates(
            config.gateway_uid_ref for config in self.gateway_configs
        )
        if duplicate_gateway_refs:
            raise ValueError(f"duplicate gateway_uid_ref values: {duplicate_gateway_refs}")

        uid_refs = [
            *(schedule.uid_ref for schedule in self.rotation_schedules),
            *(rule.uid_ref for rule in self.discovery_rules),
            *(mapping.uid_ref for mapping in self.service_mappings),
        ]
        duplicate_uid_refs = _duplicates(uid_refs)
        if duplicate_uid_refs:
            raise ValueError(f"duplicate uid_ref values: {duplicate_uid_refs}")
        return self

    def iter_object_refs(self) -> list[tuple[str, str]]:
        """Return ``(uid_ref, kind)`` for every owned offline object."""
        refs: list[tuple[str, str]] = []
        refs.extend(
            (row.gateway_uid_ref, "pam_extended_gateway_config") for row in self.gateway_configs
        )
        refs.extend(
            (row.uid_ref, "pam_extended_rotation_schedule") for row in self.rotation_schedules
        )
        refs.extend((row.uid_ref, "pam_extended_discovery_rule") for row in self.discovery_rules)
        refs.extend((row.uid_ref, "pam_extended_service_mapping") for row in self.service_mappings)
        return refs

    def iter_uid_refs(self) -> list[tuple[str, str]]:
        """Backward-compatible alias for callers that count manifest handles."""
        return self.iter_object_refs()


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def load_pam_extended_manifest(document: dict[str, Any]) -> PamExtendedManifestV1:
    """Validate with JSON Schema, then parse as ``PamExtendedManifestV1``."""
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
