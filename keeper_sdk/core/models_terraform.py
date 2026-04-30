"""Typed models for ``keeper-terraform.v1`` integration manifests.

The family is intentionally offline-only: it captures DSK/Terraform ownership
mapping metadata, but DSK must not plan or apply Terraform-managed resources.
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

TERRAFORM_FAMILY: Literal["keeper-terraform.v1"] = "keeper-terraform.v1"

DskFamily: TypeAlias = Literal[
    "pam-environment.v1",
    "keeper-vault.v1",
    "keeper-vault-sharing.v1",
    "keeper-enterprise.v1",
    "keeper-ksm.v1",
    "keeper-pam-extended.v1",
    "keeper-epm.v1",
    "keeper-integrations-identity.v1",
    "keeper-integrations-events.v1",
    "msp-environment.v1",
]
TerraformDirection: TypeAlias = Literal["dsk_source", "tf_source", "bidirectional"]
TerraformResourceType: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_]*$"),
]


class _TerraformModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)


class TerraformResourceMapping(_TerraformModel):
    """One Terraform resource type to DSK family mapping."""

    dsk_family: DskFamily
    tf_resource_type: TerraformResourceType
    direction: TerraformDirection


class TerraformIntegrationManifestV1(_TerraformModel):
    """Top-level ``keeper-terraform.v1`` integration manifest."""

    terraform_schema: Literal["keeper-terraform.v1"] = Field(
        default=TERRAFORM_FAMILY,
        alias="schema",
    )
    resource_mappings: list[TerraformResourceMapping]

    @model_validator(mode="after")
    def _resource_mappings_are_unique(self) -> TerraformIntegrationManifestV1:
        seen: set[tuple[str, str]] = set()
        duplicates: set[str] = set()
        for row in self.resource_mappings:
            key = (row.dsk_family, row.tf_resource_type)
            if key in seen:
                duplicates.add(f"{row.dsk_family}:{row.tf_resource_type}")
            seen.add(key)
        if duplicates:
            raise ValueError(f"duplicate resource_mappings: {sorted(duplicates)}")
        return self


def load_terraform_manifest(document: dict[str, object]) -> TerraformIntegrationManifestV1:
    """Validate with JSON Schema, then parse as ``TerraformIntegrationManifestV1``."""
    from keeper_sdk.core.schema import validate_manifest

    family = validate_manifest(document)
    if family != TERRAFORM_FAMILY:
        raise SchemaError(
            reason=f"expected {TERRAFORM_FAMILY!r}, got {family!r}",
            next_action="set schema: keeper-terraform.v1 on the manifest",
        )
    try:
        return TerraformIntegrationManifestV1.model_validate(document)
    except ValidationError as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-terraform.v1 typed rules",
        ) from exc
    except (ValueError, TypeError) as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-terraform.v1 typed rules",
        ) from exc


__all__ = [
    "TERRAFORM_FAMILY",
    "TerraformIntegrationManifestV1",
    "TerraformResourceMapping",
    "load_terraform_manifest",
]
