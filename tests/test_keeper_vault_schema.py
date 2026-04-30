"""keeper-vault.v1 JSON Schema contract tests."""

from __future__ import annotations

import copy
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
    / "keeper-vault"
    / "keeper-vault.v1.schema.json"
)

_MINIMAL_MANIFEST = """\
{
  "schema": "keeper-vault.v1",
  "records": [
    {
      "uid_ref": "rec.web-admin",
      "type": "login",
      "title": "Web Admin"
    }
  ]
}
"""

_FULL_MANIFEST = """\
{
  "schema": "keeper-vault.v1",
  "records": [
    {
      "uid_ref": "rec.web-admin",
      "type": "login",
      "title": "Web Admin",
      "folder_ref": "keeper-vault-sharing:folders:/Prod/Web",
      "notes": "optional",
      "fields": [
        { "type": "login", "value": ["admin@example.com"] },
        { "type": "password", "value": ["<secret>"] },
        { "type": "url", "value": ["https://admin.example.com"] },
        {
          "type": "securityQuestion",
          "value": [{ "question": "City?", "answer": "<secret>" }]
        }
      ],
      "custom": [
        { "type": "text", "label": "owner", "value": ["platform"] }
      ],
      "keeper_uid": "ABC123"
    }
  ],
  "record_types": [
    {
      "uid_ref": "rt.service-login",
      "scope": "enterprise",
      "record_type_id": 3000001,
      "content": {
        "$id": "serviceLogin",
        "categories": ["login"],
        "description": "Service login",
        "fields": [
          { "$ref": "login", "required": true },
          { "$ref": "password", "required": true },
          { "$ref": "url" }
        ]
      }
    }
  ],
  "attachments": [
    {
      "uid_ref": "att.web-admin-runbook",
      "record_uid_ref": "rec.web-admin",
      "source_path": "./attachments/runbook.pdf",
      "name": "runbook.pdf",
      "title": "Runbook",
      "mime_type": "application/pdf",
      "content_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  ],
  "keeper_fill": {
    "settings": [
      {
        "record_uid_ref": "rec.web-admin",
        "auto_fill": "on",
        "auto_submit": "off"
      }
    ]
  }
}
"""


def _schema() -> dict[str, Any]:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema


def _doc(raw: str = _MINIMAL_MANIFEST) -> dict[str, Any]:
    return json.loads(raw)


def _raise_schema_error(errors: list[jsonschema.ValidationError]) -> None:
    first = sorted(errors, key=lambda error: list(error.absolute_path))[0]
    location = "/".join(str(part) for part in first.absolute_path) or "<root>"
    raise SchemaError(
        reason=f"manifest failed schema: {first.message}",
        context={"location": location, "error_count": len(errors)},
        next_action="fix the reported fields then re-run validation",
    )


def _iter_uid_refs(document: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for collection in ("records", "record_types", "attachments"):
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


def test_keeper_vault_schema_accepts_valid_minimal_manifest() -> None:
    _validate(_doc())


def test_keeper_vault_schema_accepts_valid_full_manifest() -> None:
    _validate(_doc(_FULL_MANIFEST))


@pytest.mark.parametrize("field", ["uid_ref", "type", "title"])
def test_keeper_vault_schema_rejects_missing_required_record_field(field: str) -> None:
    document = _doc()
    del document["records"][0][field]

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert field in exc.value.reason
    assert exc.value.context["location"] == "records/0"


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ((), "unexpected"),
        (("records", 0), "unexpected"),
        (("records", 0, "fields", 0), "unexpected"),
        (("record_types", 0, "content"), "unexpected"),
        (("attachments", 0), "unexpected"),
        (("keeper_fill", "settings", 0), "unexpected"),
    ],
)
def test_keeper_vault_schema_rejects_unknown_properties(
    path: tuple[str | int, ...], field: str
) -> None:
    document = _doc(_FULL_MANIFEST)
    target: Any = document
    for part in path:
        target = target[part]
    target[field] = True

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert field in exc.value.reason


def test_keeper_vault_schema_rejects_uid_ref_collisions() -> None:
    document = _doc(_FULL_MANIFEST)
    document["record_types"][0]["uid_ref"] = "rec.web-admin"

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert "duplicate uid_ref" in exc.value.reason
    assert "rec.web-admin" in exc.value.reason


def test_keeper_vault_schema_validates_cross_family_reference_shape() -> None:
    valid = _doc(_FULL_MANIFEST)
    _validate(valid)

    invalid = copy.deepcopy(valid)
    invalid["records"][0]["folder_ref"] = "keeper_vault-sharing:folders:/Prod/Web"

    with pytest.raises(SchemaError) as exc:
        _validate(invalid)

    assert exc.value.context["location"] == "records/0/folder_ref"
