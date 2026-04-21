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
