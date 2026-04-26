"""keeper-enterprise.v1 JSON Schema contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from keeper_sdk.core import SchemaError

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "keeper_sdk"
    / "core"
    / "schemas"
    / "keeper-enterprise"
    / "keeper-enterprise.v1.schema.json"
)

_MINIMAL_MANIFEST = """\
{
  "schema": "keeper-enterprise.v1",
  "users": [
    {
      "uid_ref": "user.alice",
      "email": "alice@example.com"
    }
  ],
  "role_assignments": [
    {
      "user_uid_ref": "keeper-enterprise:users:user.alice",
      "role_uid_ref": "keeper-enterprise:roles:role.platform"
    }
  ]
}
"""

_FULL_USERS_MANIFEST = """\
{
  "schema": "keeper-enterprise.v1",
  "users": [
    {
      "uid_ref": "user.alice",
      "email": "alice@example.com",
      "name": "Alice Example",
      "node_uid_ref": "keeper-enterprise:nodes:node.platform",
      "status": "active",
      "lock_status": "unlocked",
      "pending_approval": false
    },
    {
      "uid_ref": "user.bob",
      "email": "bob@example.com",
      "name": "Bob Example",
      "node_uid_ref": "keeper-enterprise:nodes:node.platform",
      "status": "active",
      "lock_status": "unlocked",
      "pending_approval": true
    }
  ],
  "role_assignments": [
    {
      "uid_ref": "role-assign.alice.platform",
      "user_uid_ref": "keeper-enterprise:users:user.alice",
      "role_uid_ref": "keeper-enterprise:roles:role.platform",
      "is_admin": true
    },
    {
      "uid_ref": "role-assign.bob.platform",
      "user_uid_ref": "keeper-enterprise:users:user.bob",
      "role_uid_ref": "keeper-enterprise:roles:role.platform",
      "is_admin": false
    }
  ]
}
"""

_STUB_COLLECTIONS = (
    "nodes",
    "roles",
    "teams",
    "enforcements",
    "aliases",
    "enterprise_pushes",
)


def _schema() -> dict[str, Any]:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema


def _doc(raw: str = _MINIMAL_MANIFEST) -> dict[str, Any]:
    return json.loads(raw)


def _raise_schema_error(errors: list[jsonschema.ValidationError]) -> None:
    first = sorted(errors, key=lambda error: list(error.absolute_path))[0]
    location = "/".join(str(part) for part in first.absolute_path) or "<root>"
    reason = f"manifest failed schema: {first.message}"
    if location.endswith("/status") and first.validator == "enum":
        reason = f"{reason} (future-slice: only active status is in slice S)"
    raise SchemaError(
        reason=reason,
        context={"location": location, "error_count": len(errors)},
        next_action="fix the reported fields then re-run validation",
    )


def _iter_uid_refs(document: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for collection in ("users", "role_assignments"):
        for item in document.get(collection) or []:
            if isinstance(item, dict) and isinstance(item.get("uid_ref"), str):
                refs.append(item["uid_ref"])
    return refs


def _validate(document: dict[str, Any]) -> None:
    validator = jsonschema.Draft202012Validator(_schema())
    errors = list(validator.iter_errors(document))
    if errors:
        _raise_schema_error(errors)

    uid_refs = _iter_uid_refs(document)
    duplicates = sorted({uid_ref for uid_ref in uid_refs if uid_refs.count(uid_ref) > 1})
    if duplicates:
        raise SchemaError(
            reason=f"duplicate uid_ref values: {duplicates}",
            next_action="rename duplicates so every uid_ref is unique",
        )


def test_keeper_enterprise_schema_accepts_valid_minimal_manifest() -> None:
    _validate(_doc())


def test_keeper_enterprise_schema_accepts_valid_full_users_manifest() -> None:
    _validate(_doc(_FULL_USERS_MANIFEST))


@pytest.mark.parametrize("field", ["uid_ref", "email"])
def test_keeper_enterprise_schema_rejects_missing_required_user_field(field: str) -> None:
    document = _doc()
    del document["users"][0][field]

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert field in exc.value.reason
    assert exc.value.context["location"] == "users/0"


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ((), "unexpected"),
        (("users", 0), "unexpected"),
        (("role_assignments", 0), "unexpected"),
    ],
)
def test_keeper_enterprise_schema_rejects_unknown_properties(
    path: tuple[str | int, ...], field: str
) -> None:
    document = _doc()
    target: Any = document
    for part in path:
        target = target[part]
    target[field] = True

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert field in exc.value.reason


def test_keeper_enterprise_schema_rejects_reserved_future_slice_user_status() -> None:
    document = _doc(_FULL_USERS_MANIFEST)
    document["users"][0]["status"] = "locked"

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert "future-slice" in exc.value.reason
    assert exc.value.context["location"] == "users/0/status"


def test_keeper_enterprise_schema_rejects_uid_ref_collisions() -> None:
    document = _doc(_FULL_USERS_MANIFEST)
    document["role_assignments"][0]["uid_ref"] = "user.alice"

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert "duplicate uid_ref" in exc.value.reason
    assert "user.alice" in exc.value.reason


def test_keeper_enterprise_schema_accepts_unresolved_role_assignment_user_ref() -> None:
    """Cross-row reference resolution belongs to the planner, not JSON Schema."""
    document = _doc()
    document["role_assignments"][0]["user_uid_ref"] = "keeper-enterprise:users:user.missing"

    _validate(document)


def test_keeper_enterprise_schema_accepts_empty_scaffold_stub_blocks() -> None:
    document = _doc()
    for collection in _STUB_COLLECTIONS:
        document[collection] = []

    _validate(document)


@pytest.mark.parametrize("collection", _STUB_COLLECTIONS)
def test_keeper_enterprise_schema_rejects_non_empty_scaffold_stub_blocks(
    collection: str,
) -> None:
    document = _doc()
    document[collection] = [{}]

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert exc.value.context["location"] == collection
