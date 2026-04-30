"""Typed models for ``keeper-tunnel.v1`` manifests."""

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

TUNNEL_FAMILY: Literal["keeper-tunnel.v1"] = "keeper-tunnel.v1"

UidRef: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
TunnelRef: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^keeper-tunnel:tunnels:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
NonEmptyString: TypeAlias = Annotated[str, StringConstraints(min_length=1)]


class _TunnelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)


class TunnelConfig(_TunnelModel):
    """One PAM tunnel definition."""

    uid_ref: UidRef
    name: NonEmptyString
    protocol: Literal["ssh", "rdp", "http", "tcp"] = "tcp"
    enabled: bool = True


class TunnelGatewayBinding(_TunnelModel):
    """Binding between a tunnel and a gateway/configuration identity."""

    uid_ref: UidRef
    tunnel_uid_ref: TunnelRef
    gateway_uid_ref: NonEmptyString


class TunnelHostMapping(_TunnelModel):
    """One local-to-remote tunnel host mapping."""

    uid_ref: UidRef
    tunnel_uid_ref: TunnelRef
    host: NonEmptyString
    port: int = Field(ge=1, le=65535)


class TunnelManifestV1(_TunnelModel):
    """Top-level ``keeper-tunnel.v1`` manifest."""

    tunnel_schema: Literal["keeper-tunnel.v1"] = Field(default=TUNNEL_FAMILY, alias="schema")
    tunnels: list[TunnelConfig] = Field(default_factory=list)
    gateway_bindings: list[TunnelGatewayBinding] = Field(default_factory=list)
    host_mappings: list[TunnelHostMapping] = Field(default_factory=list)

    @model_validator(mode="after")
    def _refs_are_consistent(self) -> TunnelManifestV1:
        seen: dict[str, str] = {}
        duplicates: list[str] = []
        for uid_ref, kind in self.iter_uid_refs():
            if uid_ref in seen:
                duplicates.append(uid_ref)
            seen[uid_ref] = kind
        if duplicates:
            raise ValueError(f"duplicate uid_ref values: {sorted(set(duplicates))}")

        tunnels = {tunnel.uid_ref for tunnel in self.tunnels}
        missing = sorted(
            {
                _ref_uid(ref)
                for ref in [b.tunnel_uid_ref for b in self.gateway_bindings]
                + [m.tunnel_uid_ref for m in self.host_mappings]
                if _ref_uid(ref) not in tunnels
            }
        )
        if missing:
            raise ValueError(f"unknown tunnel refs: {missing}")
        return self

    def iter_uid_refs(self) -> list[tuple[str, str]]:
        refs: list[tuple[str, str]] = []
        refs.extend((tunnel.uid_ref, "tunnel") for tunnel in self.tunnels)
        refs.extend(
            (binding.uid_ref, "tunnel_gateway_binding") for binding in self.gateway_bindings
        )
        refs.extend((mapping.uid_ref, "tunnel_host_mapping") for mapping in self.host_mappings)
        return refs


def _ref_uid(ref: str) -> str:
    return ref.rsplit(":", 1)[-1]


def load_tunnel_manifest(document: dict[str, Any]) -> TunnelManifestV1:
    """Validate with JSON Schema, then parse as ``TunnelManifestV1``."""
    from keeper_sdk.core.schema import validate_manifest

    family = validate_manifest(document)
    if family != TUNNEL_FAMILY:
        raise SchemaError(
            reason=f"expected {TUNNEL_FAMILY!r}, got {family!r}",
            next_action="set schema: keeper-tunnel.v1 on the manifest",
        )
    try:
        return TunnelManifestV1.model_validate(document)
    except ValidationError as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-tunnel.v1 typed rules",
        ) from exc
    except (ValueError, TypeError) as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-tunnel.v1 typed rules",
        ) from exc


__all__ = [
    "TUNNEL_FAMILY",
    "TunnelConfig",
    "TunnelGatewayBinding",
    "TunnelHostMapping",
    "TunnelManifestV1",
    "load_tunnel_manifest",
]
