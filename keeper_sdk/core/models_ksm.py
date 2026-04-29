"""Typed models for ``keeper-ksm.v1`` manifests.

W6a ships an offline foundation only: schema validation, typed load, graph, and
field-level diff. KSM/Commander plan/apply remain future slices.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from keeper_sdk.core.errors import SchemaError

KSM_FAMILY: Literal["keeper-ksm.v1"] = "keeper-ksm.v1"

UidRef: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
AppRef: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^keeper-ksm:apps:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
RecordRef: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^keeper-vault:records:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
NonEmptyString: TypeAlias = Annotated[str, StringConstraints(min_length=1)]


class _KsmModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)


class KsmApp(_KsmModel):
    """One KSM application."""

    uid_ref: UidRef
    name: NonEmptyString
    scopes: list[NonEmptyString] = Field(default_factory=list)
    allowed_ips: list[NonEmptyString] = Field(default_factory=list)


class KsmToken(_KsmModel):
    """One KSM client token request."""

    uid_ref: UidRef
    name: NonEmptyString
    app_uid_ref: AppRef
    one_time: bool = True
    expiry: NonEmptyString | None = None


class KsmRecordShare(_KsmModel):
    """One vault-record share binding to a KSM application."""

    record_uid_ref: RecordRef
    app_uid_ref: AppRef
    editable: bool = False


class KsmConfigOutput(_KsmModel):
    """One redeemed KSM config output target."""

    app_uid_ref: AppRef
    format: Literal["json", "base64"]
    output_path: NonEmptyString


class KsmManifestV1(_KsmModel):
    """Top-level ``keeper-ksm.v1`` manifest."""

    ksm_schema: Literal["keeper-ksm.v1"] = Field(default=KSM_FAMILY, alias="schema")
    apps: list[KsmApp] = Field(default_factory=list)
    tokens: list[KsmToken] = Field(default_factory=list)
    record_shares: list[KsmRecordShare] = Field(default_factory=list)
    config_outputs: list[KsmConfigOutput] = Field(default_factory=list)

    @model_validator(mode="after")
    def _identity_keys_are_unique(self) -> KsmManifestV1:
        seen_refs: dict[str, str] = {}
        dup_refs: list[str] = []
        for uid_ref, kind in self.iter_uid_refs():
            if uid_ref in seen_refs:
                dup_refs.append(uid_ref)
            seen_refs[uid_ref] = kind
        if dup_refs:
            raise ValueError(f"duplicate uid_ref values: {sorted(set(dup_refs))}")

        share_keys = [share_key(share) for share in self.record_shares]
        dup_shares = _duplicates(share_keys)
        if dup_shares:
            raise ValueError(f"duplicate record_shares bindings: {dup_shares}")

        output_keys = [config_output_key(output) for output in self.config_outputs]
        dup_outputs = _duplicates(output_keys)
        if dup_outputs:
            raise ValueError(f"duplicate config_outputs targets: {dup_outputs}")

        return self

    def iter_uid_refs(self) -> list[tuple[str, str]]:
        """Return ``(uid_ref, kind)`` for KSM objects with first-class identity."""
        refs: list[tuple[str, str]] = []
        refs.extend((app.uid_ref, "ksm_app") for app in self.apps)
        refs.extend((token.uid_ref, "ksm_token") for token in self.tokens)
        return refs


def share_key(share: KsmRecordShare) -> str:
    """Stable synthetic key for a record-share binding."""
    return f"{share.app_uid_ref}|{share.record_uid_ref}"


def config_output_key(output: KsmConfigOutput) -> str:
    """Stable synthetic key for a config-output target."""
    return f"{output.app_uid_ref}|{output.output_path}"


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    dup: set[str] = set()
    for value in values:
        if value in seen:
            dup.add(value)
        seen.add(value)
    return sorted(dup)


def load_ksm_manifest(document: dict[str, object]) -> KsmManifestV1:
    """Validate with JSON Schema + semantic rules, then parse as ``KsmManifestV1``."""
    from keeper_sdk.core.schema import validate_manifest

    family = validate_manifest(document)
    if family != KSM_FAMILY:
        raise SchemaError(
            reason=f"expected {KSM_FAMILY!r}, got {family!r}",
            next_action="set schema: keeper-ksm.v1 on the manifest",
        )
    try:
        return KsmManifestV1.model_validate(document)
    except ValidationError as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-ksm.v1 typed rules",
        ) from exc
    except (ValueError, TypeError) as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-ksm.v1 typed rules",
        ) from exc


__all__ = [
    "KSM_FAMILY",
    "KsmApp",
    "KsmConfigOutput",
    "KsmManifestV1",
    "KsmRecordShare",
    "KsmToken",
    "config_output_key",
    "load_ksm_manifest",
    "share_key",
]
