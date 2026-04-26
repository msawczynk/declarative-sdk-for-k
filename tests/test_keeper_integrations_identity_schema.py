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
    / "keeper-integrations-identity"
    / "keeper-integrations-identity.v1.schema.json"
)

_MINIMAL_MANIFEST = """\
{
  "schema": "keeper-integrations-identity.v1",
  "domains": [
    { "uid_ref": "dom.acme", "domain": "acme.example.com" }
  ],
  "scim_endpoints": [
    {
      "uid_ref": "scim.main",
      "title": "Primary SCIM",
      "issuer_url": "https://login.microsoftonline.com/tenant-id/v2.0",
      "scim_base_url": "https://scim.acme.example.com/v2",
      "identity_provider": "azure_ad"
    }
  ],
  "email_configs": [
    {
      "uid_ref": "email.default",
      "title": "Default outbound",
      "domain_uid_ref": "keeper-integrations-identity:domains:dom.acme"
    }
  ]
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
    for collection in ("domains", "scim_endpoints", "email_configs"):
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


def test_keeper_integrations_identity_schema_accepts_minimal() -> None:
    _validate(_doc())


@pytest.mark.parametrize(
    ("collection", "field"),
    [
        ("domains", "uid_ref"),
        ("domains", "domain"),
        ("scim_endpoints", "issuer_url"),
        ("email_configs", "domain_uid_ref"),
    ],
)
def test_keeper_integrations_identity_schema_rejects_missing_required(
    collection: str, field: str
) -> None:
    document = _doc()
    del document[collection][0][field]

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert field in exc.value.reason


def test_keeper_integrations_identity_schema_rejects_unknown_property() -> None:
    document = _doc()
    document["domains"][0]["extra"] = 1

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert "extra" in exc.value.reason


def test_keeper_integrations_identity_schema_rejects_uid_ref_collision() -> None:
    document = _doc()
    document["email_configs"][0]["uid_ref"] = "dom.acme"

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert "duplicate uid_ref" in exc.value.reason


def test_keeper_integrations_identity_schema_rejects_bad_domain_fqdn() -> None:
    document = _doc()
    document["domains"][0]["domain"] = "not_a_fqdn"

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert "domain" in exc.value.context["location"]
