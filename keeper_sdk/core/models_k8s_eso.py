"""Typed models for ``keeper-k8s-eso.v1`` integration manifests.

This family is an offline bridge between DSK-owned Keeper/KSM state and
Kubernetes External Secrets Operator resources. DSK validates and renders the
Kubernetes YAML, but Kubernetes remains the resource applier.
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

K8S_ESO_FAMILY: Literal["keeper-k8s-eso.v1"] = "keeper-k8s-eso.v1"

NonEmptyString: TypeAlias = Annotated[str, StringConstraints(min_length=1)]


class _K8sEsoModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)


class EsoStore(_K8sEsoModel):
    """One ESO ``ClusterSecretStore`` backed by a Keeper KSM config secret."""

    name: NonEmptyString
    ks_uid: NonEmptyString
    namespace: NonEmptyString


class ExternalSecretData(_K8sEsoModel):
    """One Kubernetes secret key sourced from one Keeper record property."""

    keeper_uid_ref: NonEmptyString
    remote_key: NonEmptyString
    property: NonEmptyString | None = None


class ExternalSecret(_K8sEsoModel):
    """One ESO ``ExternalSecret`` mapping."""

    name: NonEmptyString
    store_ref: NonEmptyString
    target_k8s_secret: NonEmptyString
    data: list[ExternalSecretData] = Field(min_length=1)


class K8sEsoManifestV1(_K8sEsoModel):
    """Top-level ``keeper-k8s-eso.v1`` manifest."""

    k8s_eso_schema: Literal["keeper-k8s-eso.v1"] = Field(
        default=K8S_ESO_FAMILY,
        alias="schema",
    )
    eso_stores: list[EsoStore] = Field(default_factory=list)
    external_secrets: list[ExternalSecret] = Field(default_factory=list)

    @model_validator(mode="after")
    def _references_are_consistent(self) -> K8sEsoManifestV1:
        store_names = [store.name for store in self.eso_stores]
        duplicate_stores = _duplicates(store_names)
        if duplicate_stores:
            raise ValueError(f"duplicate eso_stores names: {duplicate_stores}")

        external_secret_names = [secret.name for secret in self.external_secrets]
        duplicate_external_secrets = _duplicates(external_secret_names)
        if duplicate_external_secrets:
            raise ValueError(f"duplicate external_secrets names: {duplicate_external_secrets}")

        declared_stores = set(store_names)
        missing_store_refs = sorted(
            {
                secret.store_ref
                for secret in self.external_secrets
                if secret.store_ref not in declared_stores
            }
        )
        if missing_store_refs:
            raise ValueError(f"unknown store_ref values: {missing_store_refs}")

        return self


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    dup: set[str] = set()
    for value in values:
        if value in seen:
            dup.add(value)
        seen.add(value)
    return sorted(dup)


def load_k8s_eso_manifest(document: dict[str, object]) -> K8sEsoManifestV1:
    """Validate with JSON Schema, then parse as ``K8sEsoManifestV1``."""
    from keeper_sdk.core.schema import validate_manifest

    family = validate_manifest(document)
    if family != K8S_ESO_FAMILY:
        raise SchemaError(
            reason=f"expected {K8S_ESO_FAMILY!r}, got {family!r}",
            next_action="set schema: keeper-k8s-eso.v1 on the manifest",
        )
    try:
        return K8sEsoManifestV1.model_validate(document)
    except ValidationError as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-k8s-eso.v1 typed rules",
        ) from exc
    except (ValueError, TypeError) as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-k8s-eso.v1 typed rules",
        ) from exc


__all__ = [
    "K8S_ESO_FAMILY",
    "EsoStore",
    "ExternalSecret",
    "ExternalSecretData",
    "K8sEsoManifestV1",
    "load_k8s_eso_manifest",
]
