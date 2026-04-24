"""JSON Schema validation.

Uses jsonschema if available; falls back to typed-model validation otherwise.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from keeper_sdk.core.errors import SchemaError

SCHEMA_ID = "pam-environment.v1.schema.json"


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """Load the packaged manifest schema.

    Resolution order:
      1. keeper_sdk.core.schemas package resource.
      2. Sibling workspace: keeper-pam-declarative/manifests/.
      3. Environment variable KEEPER_DECLARATIVE_SCHEMA.
    """
    import os

    # 1. packaged resource
    try:
        data = resources.files("keeper_sdk.core.schemas").joinpath(SCHEMA_ID).read_text()
        return json.loads(data)
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        pass

    # 2. sibling workspace copy
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent.parent / "keeper-pam-declarative" / "manifests" / SCHEMA_ID
        if candidate.is_file():
            return json.loads(candidate.read_text())
        candidate2 = parent / "keeper-pam-declarative" / "manifests" / SCHEMA_ID
        if candidate2.is_file():
            return json.loads(candidate2.read_text())

    # 3. env override
    override = os.environ.get("KEEPER_DECLARATIVE_SCHEMA")
    if override:
        return json.loads(Path(override).read_text())

    raise SchemaError(
        reason="manifest schema not found",
        next_action=(
            "Install keeper-declarative-sdk with its packaged schema, or set "
            "KEEPER_DECLARATIVE_SCHEMA to the path of pam-environment.v1.schema.json."
        ),
    )


def validate_manifest(document: dict[str, Any]) -> None:
    """Validate a raw manifest dict. Raises SchemaError on failure.

    Falls back to Pydantic when jsonschema is unavailable so the core still
    works in minimal environments. Semantic rules in :mod:`rules` run after
    schema validation.
    """
    from keeper_sdk.core.rules import apply_semantic_rules

    try:
        import jsonschema
    except ImportError:
        _validate_with_pydantic(document)
        apply_semantic_rules(document)
        return

    schema = load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    if not errors:
        apply_semantic_rules(document)
        return
    first = errors[0]
    location = "/".join(str(part) for part in first.absolute_path) or "<root>"
    raise SchemaError(
        reason=f"manifest failed schema: {first.message}",
        context={
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
        next_action="fix the reported fields then re-run `keeper-sdk validate`",
    )


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
