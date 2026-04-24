"""Manifest IO (YAML and JSON).

Load: parse file or string, canonicalize aliases, validate schema, build a
typed Manifest model. Dump: produce a stable canonical JSON form suitable for
git diffs and Commander interop.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from keeper_sdk.core.errors import ManifestError, SchemaError
from keeper_sdk.core.models import Manifest
from keeper_sdk.core.normalize import canonicalize
from keeper_sdk.core.preview import assert_preview_keys_allowed
from keeper_sdk.core.schema import validate_manifest


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
    data = _parse(raw, suffix)
    if not isinstance(data, dict):
        raise SchemaError(reason="manifest must be a JSON object / YAML mapping")
    document = canonicalize(data)
    if validate:
        validate_manifest(document)
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
