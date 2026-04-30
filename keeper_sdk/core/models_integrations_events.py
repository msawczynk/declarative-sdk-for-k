"""Typed models for ``keeper-integrations-events.v1`` manifests.

W15 ships an offline foundation only: schema validation, typed load, and
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
    field_validator,
    model_validator,
)

from keeper_sdk.core.errors import SchemaError

EVENTS_FAMILY: Literal["keeper-integrations-events.v1"] = "keeper-integrations-events.v1"

UidRef: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
NonEmptyString: TypeAlias = Annotated[str, StringConstraints(min_length=1)]
EmailString: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=3, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
]
Severity: TypeAlias = Literal["low", "medium", "high", "critical"]


class _EventsModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)


class EventsAutomatorRule(_EventsModel):
    """One Automator event rule row."""

    uid_ref: UidRef
    name: NonEmptyString
    trigger: Literal["record_create", "record_update", "share", "login"]
    action: Literal["webhook", "email", "slack"]
    endpoint_uid_ref: UidRef
    filter_tags: list[str] = Field(default_factory=list)


class EventsAuditAlert(_EventsModel):
    """One audit alert row."""

    uid_ref: UidRef
    name: NonEmptyString
    event_types: list[NonEmptyString]
    severity: Severity = "medium"
    notify_emails: list[EmailString]


class EventsApiKey(_EventsModel):
    """One event API key declaration."""

    uid_ref: UidRef
    name: NonEmptyString
    scopes: list[str] = Field(default_factory=list)
    expiry_days: int | None = Field(default=None, ge=1)
    ip_allowlist: list[str] = Field(default_factory=list)


class EventsEventRoute(_EventsModel):
    """One event routing declaration."""

    uid_ref: UidRef
    name: NonEmptyString
    destination_type: Literal["siem", "webhook", "email"]
    destination_uid_ref: UidRef
    filter_severity: Severity | None = None


class EventsManifestV1(_EventsModel):
    """Top-level ``keeper-integrations-events.v1`` manifest."""

    events_schema: Literal["keeper-integrations-events.v1"] = Field(
        default=EVENTS_FAMILY,
        alias="schema",
    )
    name: NonEmptyString
    manager: NonEmptyString | None = None
    automator_rules: list[EventsAutomatorRule] = Field(default_factory=list)
    audit_alerts: list[EventsAuditAlert] = Field(default_factory=list)
    api_keys: list[EventsApiKey] = Field(default_factory=list)
    event_routes: list[EventsEventRoute] = Field(default_factory=list)

    @field_validator("automator_rules", "audit_alerts", "api_keys", "event_routes")
    @classmethod
    def _collections_non_null(cls, value: list[Any]) -> list[Any]:
        return value

    @model_validator(mode="after")
    def _refs_are_unique(self) -> EventsManifestV1:
        seen_uid_refs: dict[str, str] = {}
        dup_uid_refs: list[str] = []
        for uid_ref, kind in self.iter_uid_refs():
            if uid_ref in seen_uid_refs:
                dup_uid_refs.append(uid_ref)
            seen_uid_refs[uid_ref] = kind
        if dup_uid_refs:
            raise ValueError(f"duplicate uid_ref values: {sorted(set(dup_uid_refs))}")
        return self

    def iter_uid_refs(self) -> list[tuple[str, str]]:
        """Return ``(uid_ref, kind)`` for all event objects."""
        refs: list[tuple[str, str]] = []
        refs.extend((row.uid_ref, "events_automator_rule") for row in self.automator_rules)
        refs.extend((row.uid_ref, "events_audit_alert") for row in self.audit_alerts)
        refs.extend((row.uid_ref, "events_api_key") for row in self.api_keys)
        refs.extend((row.uid_ref, "events_event_route") for row in self.event_routes)
        return refs


def load_events_manifest(document: dict[str, Any]) -> EventsManifestV1:
    """Validate with JSON Schema + semantic rules, then parse as ``EventsManifestV1``."""
    from keeper_sdk.core.schema import validate_manifest

    family = validate_manifest(document)
    if family != EVENTS_FAMILY:
        raise SchemaError(
            reason=f"expected {EVENTS_FAMILY!r}, got {family!r}",
            next_action="set schema: keeper-integrations-events.v1 on the manifest",
        )
    try:
        return EventsManifestV1.model_validate(document)
    except ValidationError as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-integrations-events.v1 typed rules",
        ) from exc
    except (ValueError, TypeError) as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-integrations-events.v1 typed rules",
        ) from exc


__all__ = [
    "EVENTS_FAMILY",
    "EventsApiKey",
    "EventsAuditAlert",
    "EventsAutomatorRule",
    "EventsEventRoute",
    "EventsManifestV1",
    "load_events_manifest",
]
