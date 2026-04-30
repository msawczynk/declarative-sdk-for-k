"""Typed models for ``keeper-siem.v1`` event streaming manifests.

The family is offline-only for this slice: DSK validates SIEM sink and
routing intent, and can compute an offline diff against a supplied snapshot.
Plan/apply remain an upstream gap until a supported Keeper writer/discover
surface exists for tenant SIEM integration configuration.
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

SIEM_FAMILY: Literal["keeper-siem.v1"] = "keeper-siem.v1"

UidRef: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
NonEmptyString: TypeAlias = Annotated[str, StringConstraints(min_length=1)]
VaultRecordRef: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^keeper-vault:records:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
SiemSinkType: TypeAlias = Literal["splunk", "datadog", "elk", "webhook", "s3"]
SiemSeverity: TypeAlias = Literal["low", "medium", "high", "critical"]


class _SiemModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)


class SiemFilter(_SiemModel):
    """Event filter applied before a sink receives audit events."""

    event_types: list[NonEmptyString] = Field(default_factory=list)
    severity_min: SiemSeverity | None = None

    @model_validator(mode="after")
    def _event_types_are_unique(self) -> SiemFilter:
        duplicates = _duplicates(self.event_types)
        if duplicates:
            raise ValueError(f"duplicate filter event_types: {duplicates}")
        return self


class SiemSink(_SiemModel):
    """One SIEM or object-storage event sink."""

    uid_ref: UidRef
    name: NonEmptyString
    type: SiemSinkType
    endpoint: NonEmptyString
    token: VaultRecordRef | None = None
    filter: SiemFilter | None = None
    batch_size: int = Field(default=500, ge=1)
    flush_interval_sec: int = Field(default=30, ge=1)


class SiemRoute(_SiemModel):
    """Route event type patterns to one or more declared sinks."""

    uid_ref: UidRef
    event_type_patterns: list[NonEmptyString] = Field(min_length=1)
    sink_uid_refs: list[UidRef] = Field(min_length=1)

    @model_validator(mode="after")
    def _lists_are_unique(self) -> SiemRoute:
        duplicate_patterns = _duplicates(self.event_type_patterns)
        if duplicate_patterns:
            raise ValueError(f"duplicate route event_type_patterns: {duplicate_patterns}")
        duplicate_sinks = _duplicates(self.sink_uid_refs)
        if duplicate_sinks:
            raise ValueError(f"duplicate route sink_uid_refs: {duplicate_sinks}")
        return self


class SiemManifestV1(_SiemModel):
    """Top-level ``keeper-siem.v1`` manifest."""

    siem_schema: Literal["keeper-siem.v1"] = Field(default=SIEM_FAMILY, alias="schema")
    name: NonEmptyString | None = None
    manager: NonEmptyString | None = None
    sinks: list[SiemSink] = Field(default_factory=list)
    routes: list[SiemRoute] = Field(default_factory=list)

    @model_validator(mode="after")
    def _refs_are_consistent(self) -> SiemManifestV1:
        seen_uid_refs: dict[str, str] = {}
        dup_uid_refs: list[str] = []
        for uid_ref, kind in self.iter_uid_refs():
            if uid_ref in seen_uid_refs:
                dup_uid_refs.append(uid_ref)
            seen_uid_refs[uid_ref] = kind
        if dup_uid_refs:
            raise ValueError(f"duplicate uid_ref values: {sorted(set(dup_uid_refs))}")

        declared_sinks = {sink.uid_ref for sink in self.sinks}
        missing_sink_refs = sorted(
            {
                sink_ref
                for route in self.routes
                for sink_ref in route.sink_uid_refs
                if sink_ref not in declared_sinks
            }
        )
        if missing_sink_refs:
            raise ValueError(f"unknown route sink_uid_refs: {missing_sink_refs}")
        return self

    def iter_uid_refs(self) -> list[tuple[str, str]]:
        """Return ``(uid_ref, kind)`` for SIEM objects declared by this manifest."""
        refs: list[tuple[str, str]] = []
        refs.extend((sink.uid_ref, "siem_sink") for sink in self.sinks)
        refs.extend((route.uid_ref, "siem_route") for route in self.routes)
        return refs


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    dup: set[str] = set()
    for value in values:
        if value in seen:
            dup.add(value)
        seen.add(value)
    return sorted(dup)


def load_siem_manifest(document: dict[str, Any]) -> SiemManifestV1:
    """Validate with JSON Schema + semantic rules, then parse as ``SiemManifestV1``."""
    from keeper_sdk.core.schema import validate_manifest

    family = validate_manifest(document)
    if family != SIEM_FAMILY:
        raise SchemaError(
            reason=f"expected {SIEM_FAMILY!r}, got {family!r}",
            next_action="set schema: keeper-siem.v1 on the manifest",
        )
    try:
        return SiemManifestV1.model_validate(document)
    except ValidationError as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-siem.v1 typed rules",
        ) from exc
    except (ValueError, TypeError) as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-siem.v1 typed rules",
        ) from exc


__all__ = [
    "SIEM_FAMILY",
    "SiemFilter",
    "SiemManifestV1",
    "SiemRoute",
    "SiemSink",
    "load_siem_manifest",
]
