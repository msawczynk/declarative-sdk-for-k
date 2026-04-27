"""Typed models for ``msp-environment.v1`` manifests (PAM parity program, MSP slice 1).

Slice 1 per ``docs/MSP_FAMILY_DESIGN.md``: top-level ``managed_companies[]`` with
structured ``addons`` (name + seats). Plan/apply and graph live in follow-on slices.

Load via :func:`~keeper_sdk.core.manifest.load_declarative_manifest` (or
:func:`load_msp_manifest` after :func:`~keeper_sdk.core.schema.validate_manifest`).
:func:`~keeper_sdk.core.manifest.load_manifest` is **PAM-only** and refuses this family.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from keeper_sdk.core.errors import SchemaError

MSP_FAMILY: Literal["msp-environment.v1"] = "msp-environment.v1"
_DUPLICATE_MC_NAME_NEXT_ACTION = "rename one managed_company; names must be unique case-insensitively"


class _MspModel(BaseModel):
    """Permissive leaf blocks so schema growth does not break reads."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, str_strip_whitespace=True)


class Addon(_MspModel):
    """One ``addons[]`` entry (``$defs.addon`` in the packaged schema)."""

    name: str = Field(min_length=1)
    seats: int = Field(ge=0)


class ManagedCompany(_MspModel):
    """One ``managed_companies[]`` entry."""

    name: str = Field(min_length=1)
    plan: str = Field(min_length=1)
    seats: int = Field(ge=0)
    file_plan: str | None = None
    addons: list[Addon] = Field(default_factory=list)


class MspManifestV1(_MspModel):
    """Top-level ``msp-environment.v1`` manifest (slice 1)."""

    msp_schema: Literal["msp-environment.v1"] = Field(default=MSP_FAMILY, alias="schema")
    name: str = Field(min_length=1)
    manager: str | None = None
    managed_companies: list[ManagedCompany] = Field(default_factory=list)
    policies: dict[str, Any] = Field(default_factory=dict)


def load_msp_manifest(document: dict[str, Any]) -> MspManifestV1:
    """Validate with JSON Schema + semantic rules, then parse as :class:`MspManifestV1`."""

    from keeper_sdk.core.schema import validate_manifest

    if document.get("schema") == MSP_FAMILY:
        _reject_duplicate_managed_company_names(document)

    family = validate_manifest(document)
    if family != MSP_FAMILY:
        raise SchemaError(
            reason=f"expected {MSP_FAMILY!r}, got {family!r}",
            next_action="set schema: msp-environment.v1 and see docs/MSP_FAMILY_DESIGN.md",
        )
    try:
        return MspManifestV1.model_validate(document)
    except ValidationError as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match docs/MSP_FAMILY_DESIGN.md and the packaged msp schema",
        ) from exc
    except (ValueError, TypeError) as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match docs/MSP_FAMILY_DESIGN.md and the packaged msp schema",
        ) from exc


def _reject_duplicate_managed_company_names(document: dict[str, Any]) -> None:
    seen: dict[str, str] = {}
    for row in document.get("managed_companies") or []:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not isinstance(name, str):
            continue
        key = name.casefold()
        if key in seen:
            raise SchemaError(
                reason=(
                    "managed_companies has duplicate name case-insensitively: "
                    f"{seen[key]!r} and {name!r}"
                ),
                next_action=_DUPLICATE_MC_NAME_NEXT_ACTION,
            )
        seen[key] = name


__all__ = [
    "MSP_FAMILY",
    "Addon",
    "ManagedCompany",
    "MspManifestV1",
    "load_msp_manifest",
]
