"""Manifest IO (YAML and JSON).

Parse paths or strings, canonicalise aliases, validate schema, build **typed**
models. **PAM only:** :func:`load_manifest` / :func:`load_manifest_string` →
:class:`~keeper_sdk.core.models.Manifest`. **PAM + vault L1 + sharing L1:**
:func:`load_declarative_manifest` / :func:`load_declarative_manifest_string` →
``Manifest``, :class:`~keeper_sdk.core.vault_models.VaultManifestV1` for
``keeper-vault.v1``, or :class:`~keeper_sdk.core.sharing_models.SharingManifestV1`
for ``keeper-vault-sharing.v1``.
Dump: stable canonical YAML/JSON for git diffs and Commander interop.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from keeper_sdk.core.errors import ManifestError, SchemaError
from keeper_sdk.core.models import Manifest
from keeper_sdk.core.normalize import canonicalize
from keeper_sdk.core.preview import assert_preview_keys_allowed
from keeper_sdk.core.schema import PAM_FAMILY, validate_manifest
from keeper_sdk.core.sharing_models import SHARING_FAMILY, load_sharing_manifest

if TYPE_CHECKING:
    from keeper_sdk.core.sharing_models import SharingManifestV1
    from keeper_sdk.core.vault_models import VaultManifestV1


def read_manifest_document(source: str | Path) -> dict[str, Any]:
    """Parse + canonicalise a manifest file without typed-model load.

    Used by ``dsk validate`` for non-PAM families and by tests.
    """
    path = Path(source)
    if not path.is_file():
        raise ManifestError(reason=f"manifest not found: {path}", next_action="check the path")
    raw = path.read_text(encoding="utf-8")
    return read_manifest_document_string(raw, suffix=path.suffix)


def read_manifest_document_string(raw: str, *, suffix: str = ".yaml") -> dict[str, Any]:
    data = _parse(raw, suffix)
    if not isinstance(data, dict):
        raise SchemaError(reason="manifest must be a JSON object / YAML mapping")
    return canonicalize(data)


def load_manifest(source: str | Path, *, validate: bool = True) -> Manifest:
    """Load a manifest from a path.

    Supports ``.yaml``, ``.yml``, ``.json``. Always returns a typed Manifest.
    """
    path = Path(source)
    if not path.is_file():
        raise ManifestError(reason=f"manifest not found: {path}", next_action="check the path")

    raw = path.read_text(encoding="utf-8")
    return load_manifest_string(raw, suffix=path.suffix, validate=validate)


def load_manifest_string(raw: str, *, suffix: str = ".yaml", validate: bool = True) -> Manifest:
    document = read_manifest_document_string(raw, suffix=suffix)
    if validate:
        family = validate_manifest(document)
        if family != PAM_FAMILY:
            raise ManifestError(
                reason=(
                    f"typed manifest load supports {PAM_FAMILY} only (document declares {family})"
                ),
                next_action=(
                    "for keeper-vault.v1 use load_declarative_manifest(); "
                    "for schema-only checks use read_manifest_document + validate_manifest; "
                    "see docs/PAM_PARITY_PROGRAM.md for other families."
                ),
            )
        # Schema accepts more than the SDK implements; the preview gate
        # closes that gap at load time with a one-line remediation
        # (DSK_PREVIEW=1) instead of forcing operators to read plan
        # output to find out their manifest is half-declarative.
        assert_preview_keys_allowed(document)
    try:
        return Manifest.model_validate(document)
    except (ValueError, TypeError) as exc:  # pydantic ValidationError subclasses ValueError
        raise SchemaError(
            reason=f"typed validation failed: {exc}",
            next_action="fix the reported fields",
        ) from exc


def load_declarative_manifest(
    source: str | Path, *, validate: bool = True
) -> Manifest | VaultManifestV1 | SharingManifestV1:
    """Load a typed manifest for families the engine can plan (PAM + vault/sharing L1).

    Returns :class:`~keeper_sdk.core.models.Manifest` for ``pam-environment.v1``
    or :class:`~keeper_sdk.core.vault_models.VaultManifestV1` for
    ``keeper-vault.v1``, or
    :class:`~keeper_sdk.core.sharing_models.SharingManifestV1` for
    ``keeper-vault-sharing.v1``. Other schema-valid families raise
    :class:`ManifestError` (use :func:`read_manifest_document` +
    :func:`validate_manifest` for schema-only checks).

    ``keeper-vault.v1`` and ``keeper-vault-sharing.v1`` do not use the PAM
    preview gate.
    """
    path = Path(source)
    if not path.is_file():
        raise ManifestError(reason=f"manifest not found: {path}", next_action="check the path")
    raw = path.read_text(encoding="utf-8")
    return load_declarative_manifest_string(raw, suffix=path.suffix, validate=validate)


def load_declarative_manifest_string(
    raw: str, *, suffix: str = ".yaml", validate: bool = True
) -> Manifest | VaultManifestV1 | SharingManifestV1:
    from keeper_sdk.core.vault_models import VAULT_FAMILY, load_vault_manifest

    document = read_manifest_document_string(raw, suffix=suffix)
    if not validate:
        raise ManifestError(
            reason="load_declarative_manifest_string requires validate=True",
            next_action="parse with read_manifest_document_string then validate_manifest",
        )
    family = validate_manifest(document)
    if family == PAM_FAMILY:
        assert_preview_keys_allowed(document)
        try:
            return Manifest.model_validate(document)
        except (ValueError, TypeError) as exc:
            raise SchemaError(
                reason=f"typed validation failed: {exc}",
                next_action="fix the reported fields",
            ) from exc
    if family == VAULT_FAMILY:
        return load_vault_manifest(document)
    if family == SHARING_FAMILY:
        return load_sharing_manifest(document)
    raise ManifestError(
        reason=(
            f"typed plan/load supports {PAM_FAMILY}, {VAULT_FAMILY}, "
            f"and {SHARING_FAMILY} only "
            f"(document declares {family!r})"
        ),
        next_action=(
            "use `dsk validate` for schema-only checks on other families; "
            "see docs/PAM_PARITY_PROGRAM.md"
        ),
    )


def dump_manifest(manifest: Manifest, *, fmt: str = "yaml") -> str:
    """Serialize a Manifest back to canonical YAML or JSON.

    Drops ``None`` fields so the output matches the hand-authored style.
    """
    data = manifest.model_dump(mode="json", exclude_none=True, by_alias=False)
    if fmt == "json":
        return json.dumps(data, indent=2, sort_keys=False)
    if fmt == "yaml":
        import yaml

        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    raise ValueError(f"unsupported dump format: {fmt}")


def _parse(raw: str, suffix: str) -> Any:
    if suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise ManifestError(
                reason="pyyaml is required to load YAML manifests",
                next_action="`pip install pyyaml`",
            ) from exc
        return yaml.safe_load(raw)
    if suffix.lower() == ".json":
        return json.loads(raw)
    # autodetect
    stripped = raw.lstrip()
    if stripped.startswith("{"):
        return json.loads(raw)
    import yaml

    return yaml.safe_load(raw)
