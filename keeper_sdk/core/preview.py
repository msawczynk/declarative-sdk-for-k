"""Preview-key gate: reject manifest keys whose implementation is deferred.

The JSON Schema accepts a wider surface than any provider currently
drives — ``rotation_settings``, ``jit_settings``, gateway
``mode: create``, ``default_rotation_schedule``, and top-level
``projects[]``. Without this gate, ``validate`` returns clean, ``plan``
produces CONFLICT rows, and the operator has to read plan output to
discover that half their manifest is a no-op. Failing at validate
time, with one specific line of remediation, is cheaper.

To declare that you know the keys are preview and want to proceed (for
example with the mock provider, for forward-compatibility testing, or
once a future version implements one of them), set ``DSK_PREVIEW=1``.

The gate is orthogonal to
:meth:`keeper_sdk.core.interfaces.Provider.unsupported_capabilities`:

- Schema-preview: "are you ALLOWED to declare this at all?"
- Provider-capability: "can THIS provider drive what you declared?"

A manifest with ``DSK_PREVIEW=1`` containing ``rotation_settings`` is
accepted by validate, survives plan against the mock provider, and
still produces a CONFLICT row against the commander provider. Both
layers are needed — one stops honest-but-clueless authors at the
door, the other stops plan/apply skew at the provider boundary.

The preview key list lives here (not in the schema) because it is a
property of the SDK release, not of the manifest format. A v1.1 that
implements rotation moves ``rotation_settings`` from preview to GA
without schema change.
"""

from __future__ import annotations

import os
from typing import Any

from keeper_sdk.core.errors import SchemaError

#: ``(needle, human_name, removal_version)`` — ``needle`` is matched as
#: an exact nested key. Add entries here when the schema grows a key before
#: any provider drives it; remove entries once the first provider implements
#: the feature.
PREVIEW_KEYS: tuple[tuple[str, str, str], ...] = (
    (
        "rotation_settings",
        "users[].rotation_settings / resources[].users[].rotation_settings",
        "planned for 1.1",
    ),
    (
        "default_rotation_schedule",
        "pam_configurations[].default_rotation_schedule",
        "planned for 1.1",
    ),
    ("jit_settings", "jit_settings (per-resource or per-config)", "planned for 1.2"),
    ("rotation_schedule", "rotation_schedule (embedded)", "planned for 1.1"),
)

PREVIEW_ENV_VAR = "DSK_PREVIEW"


def preview_is_enabled() -> bool:
    """True iff ``DSK_PREVIEW`` is set to a truthy string.

    Recognised truthy values: ``1``, ``true``, ``yes``, ``on``
    (case-insensitive). Anything else — including the empty string,
    ``0``, ``false`` — is treated as disabled.
    """
    raw = os.environ.get(PREVIEW_ENV_VAR, "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _contains_key(node: Any, key: str) -> bool:
    if isinstance(node, dict):
        return key in node or any(_contains_key(value, key) for value in node.values())
    if isinstance(node, list):
        return any(_contains_key(item, key) for item in node)
    return False


def detect_preview_keys(manifest: dict[str, Any]) -> list[str]:
    """Return human-readable descriptions of preview keys present.

    Pure detector; does not consult the env var. Callers decide
    whether to raise based on :func:`preview_is_enabled`.
    """
    hits: list[str] = []

    gateways = manifest.get("gateways")
    if isinstance(gateways, list):
        for gateway in gateways:
            if isinstance(gateway, dict) and gateway.get("mode") == "create":
                hits.append(
                    f"gateway '{gateway.get('uid_ref') or gateway.get('name')}': "
                    "mode: create (planned for 1.2)"
                )

    if manifest.get("projects"):
        hits.append("top-level projects[] (planned for 1.2)")

    for needle, human, removal_version in PREVIEW_KEYS:
        if _contains_key(manifest, needle):
            hits.append(f"{human} ({removal_version})")

    return hits


def assert_preview_keys_allowed(manifest: dict[str, Any]) -> None:
    """Raise :class:`SchemaError` if preview keys are present without opt-in.

    Called by :func:`keeper_sdk.core.manifest.load_manifest_string`
    immediately after schema validation. Silent no-op when
    ``DSK_PREVIEW=1`` or when the manifest is clean.
    """
    if preview_is_enabled():
        return
    hits = detect_preview_keys(manifest)
    if not hits:
        return
    raise SchemaError(
        reason=(
            "manifest declares preview keys the current SDK does not implement: " + "; ".join(hits)
        ),
        next_action=(
            f"remove the listed keys, or export {PREVIEW_ENV_VAR}=1 to accept "
            "preview keys (they will still surface as plan-time CONFLICT rows "
            "against the commander provider until the implementation lands)"
        ),
    )
