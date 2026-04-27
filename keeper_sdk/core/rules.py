"""Semantic rules layered on top of JSON Schema.

JSON Schema can't easily express a few of our invariants:

  1. ``gateway.mode == "create"`` requires ``ksm_application_name`` and the
     caller to have KSM app creation permission.
  2. ``pamRemoteBrowser`` cannot carry a ``rotation`` option (schema already
     enforces; this rule provides a cleaner message).
  3. Unknown ``uid_ref`` targets (handled in :mod:`graph`).

``apply_semantic_rules`` runs after JSON Schema and before graph construction.
"""

from __future__ import annotations

from typing import Any

from keeper_sdk.core.errors import CapabilityError, SchemaError


def apply_semantic_rules(document: dict[str, Any]) -> None:
    """Run cheap post-schema checks. Raises on failure."""
    for gateway in document.get("gateways") or []:
        if gateway.get("mode") == "create" and not gateway.get("ksm_application_name"):
            raise CapabilityError(
                reason="gateway mode='create' requires ksm_application_name",
                uid_ref=gateway.get("uid_ref"),
                resource_type="gateway",
                next_action=(
                    "set ksm_application_name on the gateway, or change mode to "
                    "'reference_existing' and register the gateway manually."
                ),
            )

    for resource in document.get("resources") or []:
        if resource.get("type") == "pamRemoteBrowser":
            options = ((resource.get("pam_settings") or {}).get("options")) or {}
            if "rotation" in options:
                raise SchemaError(
                    reason="pamRemoteBrowser cannot set rotation in options",
                    uid_ref=resource.get("uid_ref"),
                    resource_type="pamRemoteBrowser",
                    next_action="remove rotation from pam_settings.options",
                )

    if document.get("pam_configurations"):
        for resource in document.get("resources") or []:
            if not resource.get("pam_configuration_uid_ref"):
                raise SchemaError(
                    reason=(
                        f"resource '{resource.get('uid_ref')}' must set "
                        "pam_configuration_uid_ref because pam_configurations "
                        "are declared"
                    ),
                    uid_ref=resource.get("uid_ref"),
                    resource_type=resource.get("type"),
                    next_action=(
                        "set pam_configuration_uid_ref on the resource or remove "
                        "all pam_configurations"
                    ),
                )

    if document.get("schema") == "msp-environment.v1":
        seen: set[str] = set()
        for mc in document.get("managed_companies") or []:
            if not isinstance(mc, dict):
                continue
            raw_name = mc.get("name")
            if not isinstance(raw_name, str):
                continue
            if raw_name in seen:
                raise SchemaError(
                    reason=f"managed_companies has duplicate name {raw_name!r}",
                    next_action=(
                        "rename or remove the duplicate; manifest names must be "
                        "unique within msp-environment.v1"
                    ),
                )
            seen.add(raw_name)

    rotatable_resource_types = {"pamMachine", "pamDatabase", "pamDirectory"}
    for resource in document.get("resources") or []:
        resource_type = resource.get("type")
        options = ((resource.get("pam_settings") or {}).get("options")) or {}

        if resource_type == "pamRemoteBrowser" and options.get("jit_settings"):
            raise SchemaError(
                reason="pamRemoteBrowser does not support jit_settings",
                uid_ref=resource.get("uid_ref"),
                resource_type="pamRemoteBrowser",
                next_action="remove jit_settings from pam_settings.options",
            )

        if resource_type not in rotatable_resource_types and "rotation" in options:
            raise SchemaError(
                reason=f"rotation is not supported for {resource_type}",
                uid_ref=resource.get("uid_ref"),
                resource_type=resource_type,
                next_action="remove rotation from pam_settings.options",
            )
