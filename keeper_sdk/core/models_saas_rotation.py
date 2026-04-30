"""Typed models for ``keeper-saas-rotation.v1`` manifests."""

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

SAAS_ROTATION_FAMILY: Literal["keeper-saas-rotation.v1"] = "keeper-saas-rotation.v1"

UidRef: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
SaaSRotationRef: TypeAlias = Annotated[
    str,
    StringConstraints(
        pattern=r"^keeper-saas-rotation:rotations:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
    ),
]
VaultRecordRef: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^keeper-vault:records:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
NonEmptyString: TypeAlias = Annotated[str, StringConstraints(min_length=1)]


class _SaaSRotationModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)


class SaaSRotationConfig(_SaaSRotationModel):
    """One SaaS rotation policy/configuration."""

    uid_ref: UidRef
    name: NonEmptyString
    provider: NonEmptyString
    schedule: NonEmptyString | None = None
    enabled: bool = True


class SaaSRotationBinding(_SaaSRotationModel):
    """Binding from a SaaS rotation config to a Keeper record."""

    uid_ref: UidRef
    rotation_uid_ref: SaaSRotationRef
    record_uid_ref: VaultRecordRef
    account: NonEmptyString | None = None


class SaaSRotationManifestV1(_SaaSRotationModel):
    """Top-level ``keeper-saas-rotation.v1`` manifest."""

    saas_rotation_schema: Literal["keeper-saas-rotation.v1"] = Field(
        default=SAAS_ROTATION_FAMILY,
        alias="schema",
    )
    rotations: list[SaaSRotationConfig] = Field(default_factory=list)
    bindings: list[SaaSRotationBinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def _refs_are_consistent(self) -> SaaSRotationManifestV1:
        seen: dict[str, str] = {}
        duplicates: list[str] = []
        for uid_ref, kind in self.iter_uid_refs():
            if uid_ref in seen:
                duplicates.append(uid_ref)
            seen[uid_ref] = kind
        if duplicates:
            raise ValueError(f"duplicate uid_ref values: {sorted(set(duplicates))}")

        rotations = {rotation.uid_ref for rotation in self.rotations}
        missing = sorted(
            {
                _ref_uid(binding.rotation_uid_ref)
                for binding in self.bindings
                if _ref_uid(binding.rotation_uid_ref) not in rotations
            }
        )
        if missing:
            raise ValueError(f"unknown SaaS rotation refs: {missing}")
        return self

    def iter_uid_refs(self) -> list[tuple[str, str]]:
        refs: list[tuple[str, str]] = []
        refs.extend((rotation.uid_ref, "saas_rotation") for rotation in self.rotations)
        refs.extend((binding.uid_ref, "saas_rotation_binding") for binding in self.bindings)
        return refs


def _ref_uid(ref: str) -> str:
    return ref.rsplit(":", 1)[-1]


def load_saas_rotation_manifest(document: dict[str, Any]) -> SaaSRotationManifestV1:
    """Validate with JSON Schema, then parse as ``SaaSRotationManifestV1``."""
    from keeper_sdk.core.schema import validate_manifest

    family = validate_manifest(document)
    if family != SAAS_ROTATION_FAMILY:
        raise SchemaError(
            reason=f"expected {SAAS_ROTATION_FAMILY!r}, got {family!r}",
            next_action="set schema: keeper-saas-rotation.v1 on the manifest",
        )
    try:
        return SaaSRotationManifestV1.model_validate(document)
    except ValidationError as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-saas-rotation.v1 typed rules",
        ) from exc
    except (ValueError, TypeError) as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-saas-rotation.v1 typed rules",
        ) from exc


__all__ = [
    "SAAS_ROTATION_FAMILY",
    "SaaSRotationBinding",
    "SaaSRotationConfig",
    "SaaSRotationManifestV1",
    "load_saas_rotation_manifest",
]
