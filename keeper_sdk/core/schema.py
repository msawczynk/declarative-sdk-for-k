"""JSON Schema validation.

Uses jsonschema if available; falls back to typed-model validation for
``pam-environment.v1`` only when jsonschema is missing.

Phase 0 (PAM parity program): every packaged ``*.v1`` family resolves via
``schema: <family>.v1`` (or legacy ``version`` + ``name`` for PAM). See
``docs/PAM_PARITY_PROGRAM.md``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from keeper_sdk.core.errors import SchemaError

PAM_FAMILY = "pam-environment.v1"
ENTERPRISE_FAMILY = "keeper-enterprise.v1"
IDENTITY_FAMILY = "keeper-integrations-identity.v1"
EVENTS_FAMILY = "keeper-integrations-events.v1"
KSM_FAMILY = "keeper-ksm.v1"
SHARING_FAMILY = "keeper-vault-sharing.v1"
PAM_EXTENDED_FAMILY = "keeper-pam-extended.v1"
PAM_SCHEMA_FILENAME = "pam-environment.v1.schema.json"

# Canonical registry: manifest ``schema:`` const -> path under keeper_sdk.core.schemas
SCHEMA_RESOURCE_BY_FAMILY: dict[str, str] = {
    PAM_FAMILY: PAM_SCHEMA_FILENAME,
    ENTERPRISE_FAMILY: "enterprise/enterprise.v1.schema.json",
    "keeper-epm.v1": "keeper-epm/keeper-epm.v1.schema.json",
    EVENTS_FAMILY: "integrations/events.v1.schema.json",
    IDENTITY_FAMILY: "integrations/identity.v1.schema.json",
    KSM_FAMILY: "ksm/ksm.v1.schema.json",
    PAM_EXTENDED_FAMILY: "pam_extended/pam_extended.v1.schema.json",
    "keeper-security-posture.v1": (
        "keeper-security-posture/keeper-security-posture.v1.schema.json"
    ),
    SHARING_FAMILY: "keeper-vault-sharing/keeper-vault-sharing.v1.schema.json",
    "keeper-vault.v1": "keeper-vault/keeper-vault.v1.schema.json",
    "msp-environment.v1": "msp-environment/msp-environment.v1.schema.json",
}

# Backward-compat alias used by older imports / docs.
SCHEMA_ID = PAM_SCHEMA_FILENAME


def resolve_manifest_family(document: dict[str, Any]) -> str:
    """Return the manifest family key (e.g. ``pam-environment.v1``).

    New families declare ``schema: "<family>.v1"``. Legacy PAM manifests omit
    ``schema`` and use ``version: "1"`` plus ``name``.
    """
    raw = document.get("schema")
    if isinstance(raw, str) and raw.strip():
        key = raw.strip()
        if key not in SCHEMA_RESOURCE_BY_FAMILY:
            known = ", ".join(sorted(SCHEMA_RESOURCE_BY_FAMILY))
            raise SchemaError(
                reason=f"unknown manifest schema {key!r}",
                next_action=f"use a packaged family key: {known}",
            )
        return key

    if document.get("version") == "1" and isinstance(document.get("name"), str):
        name = document.get("name")
        assert isinstance(name, str)
        if name.strip():
            return PAM_FAMILY

    raise SchemaError(
        reason="manifest must declare schema: <family>.v1 or legacy PAM fields version+name",
        next_action=(
            "for PAM examples use version: '1' and name: ...; for other families set "
            "schema: keeper-vault.v1 (etc.)"
        ),
    )


def _read_packaged_schema_bytes(family: str) -> str:
    rel = SCHEMA_RESOURCE_BY_FAMILY[family]
    try:
        root = resources.files("keeper_sdk.core.schemas")
    except (FileNotFoundError, ModuleNotFoundError, AttributeError, OSError, TypeError) as exc:
        raise SchemaError(
            reason=f"packaged schema namespace unavailable for {family}",
            next_action="reinstall keeper_sdk or report a packaging bug",
        ) from exc
    node = root.joinpath(rel)
    try:
        return node.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise SchemaError(
            reason=f"packaged schema not found for {family} ({rel})",
            next_action="reinstall keeper_sdk or report a packaging bug",
        ) from exc


def _read_pam_schema_from_sibling_or_env() -> dict[str, Any] | None:
    """Legacy fallbacks for ``pam-environment.v1`` only (dev trees without wheel)."""
    import os

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent.parent / "keeper-pam-declarative" / "manifests" / PAM_SCHEMA_FILENAME
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
        candidate2 = parent / "keeper-pam-declarative" / "manifests" / PAM_SCHEMA_FILENAME
        if candidate2.is_file():
            return json.loads(candidate2.read_text(encoding="utf-8"))

    override = os.environ.get("KEEPER_DECLARATIVE_SCHEMA")
    if override:
        return json.loads(Path(override).read_text(encoding="utf-8"))
    return None


@lru_cache(maxsize=len(SCHEMA_RESOURCE_BY_FAMILY))
def load_schema_for_family(family: str) -> dict[str, Any]:
    """Load the packaged JSON Schema dict for *family* (const matches ``schema:``)."""
    if family not in SCHEMA_RESOURCE_BY_FAMILY:
        raise SchemaError(
            reason=f"unknown schema family {family!r}",
            next_action="use resolve_manifest_family or SCHEMA_RESOURCE_BY_FAMILY keys",
        )

    if family == PAM_FAMILY:
        try:
            text = _read_packaged_schema_bytes(PAM_FAMILY)
            return json.loads(text)
        except (
            SchemaError,
            FileNotFoundError,
            OSError,
            ModuleNotFoundError,
            AttributeError,
            TypeError,
            ValueError,
        ):
            blob = _read_pam_schema_from_sibling_or_env()
            if blob is not None:
                return blob
            raise SchemaError(
                reason="manifest schema not found",
                next_action=(
                    "Install keeper_sdk with packaged schemas, or set "
                    "KEEPER_DECLARATIVE_SCHEMA to pam-environment.v1.schema.json, "
                    "or clone keeper-pam-declarative alongside this repo."
                ),
            ) from None

    text = _read_packaged_schema_bytes(family)
    return json.loads(text)


def load_schema() -> dict[str, Any]:
    """Load **pam-environment.v1** schema (backward-compatible alias)."""
    return load_schema_for_family(PAM_FAMILY)


def _assert_family_not_dropped(schema: dict[str, Any], *, family: str) -> None:
    block = schema.get("x-keeper-live-proof")
    if not isinstance(block, dict):
        return
    status = block.get("status")
    if status == "dropped-design":
        raise SchemaError(
            reason=(
                f"manifest family {family} is dropped-design — it cannot be used as a "
                "declarative manifest (see docs/V2_DECISIONS.md Q1/Q3)."
            ),
            next_action=(
                "remove the schema pin or use the supported `dsk report` verbs for "
                "read-only posture output."
            ),
        )


def validate_manifest(document: dict[str, Any]) -> str:
    """Validate *document* against its family's JSON Schema.

    Returns the resolved family key (e.g. ``pam-environment.v1``).

    Raises :class:`SchemaError` if the family is ``dropped-design`` or the
    document fails schema / semantic rules.
    """
    from keeper_sdk.core.rules import apply_semantic_rules

    family = resolve_manifest_family(document)

    try:
        import jsonschema
    except ImportError:
        if family != PAM_FAMILY:
            raise SchemaError(
                reason="jsonschema is required to validate non-PAM manifest families",
                next_action="pip install jsonschema",
            ) from None
        _validate_with_pydantic(document)
        apply_semantic_rules(document)
        return family

    schema = load_schema_for_family(family)
    _assert_family_not_dropped(schema, family=family)

    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    if errors:
        enterprise_stub_error = _enterprise_legacy_stub_error(
            family=family,
            document=document,
            error_count=len(errors),
        )
        if enterprise_stub_error is not None:
            raise enterprise_stub_error
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "<root>"
        raise SchemaError(
            reason=f"manifest failed schema: {first.message}",
            context={
                "family": family,
                "location": location,
                "error_count": len(errors),
                "additional": [
                    {
                        "path": "/".join(str(part) for part in extra.absolute_path),
                        "message": extra.message,
                    }
                    for extra in errors[1:5]
                ],
            },
            next_action="fix the reported fields then re-run `dsk validate`",
        )

    apply_semantic_rules(document)
    return family


def _enterprise_legacy_stub_error(
    *,
    family: str,
    document: dict[str, Any],
    error_count: int,
) -> SchemaError | None:
    """Keep the old Phase-7 empty-stub failure copy for partial team/role rows."""
    if family != ENTERPRISE_FAMILY:
        return None
    for collection in ("teams", "roles"):
        rows = document.get(collection)
        if not isinstance(rows, list) or not rows:
            continue
        if not all(_is_legacy_team_role_stub(row) for row in rows):
            continue
        return SchemaError(
            reason=(
                f"manifest failed schema: {collection} is expected to be empty unless "
                "rows use the full keeper-enterprise.v1 shape"
            ),
            context={
                "family": family,
                "location": collection,
                "error_count": error_count,
                "additional": [],
            },
            next_action="add node_uid_ref and supported membership fields, or leave the block empty",
        )
    return None


def _is_legacy_team_role_stub(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    return set(row).issubset({"uid_ref", "name"})


def _validate_with_pydantic(document: dict[str, Any]) -> None:
    from pydantic import ValidationError

    from keeper_sdk.core.models import Manifest

    try:
        Manifest.model_validate(document)
    except ValidationError as exc:
        raise SchemaError(
            reason="manifest failed typed validation",
            context={"errors": exc.errors()[:5], "error_count": len(exc.errors())},
            next_action="fix the reported fields then re-run `keeper-sdk validate`",
        ) from exc


def packaged_schema_families() -> tuple[str, ...]:
    """Stable list of family keys shipped in ``keeper_sdk.core.schemas``."""
    return tuple(sorted(SCHEMA_RESOURCE_BY_FAMILY.keys()))
