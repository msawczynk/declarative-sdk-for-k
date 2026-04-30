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
    / "keeper-integrations-events"
    / "keeper-integrations-events.v1.schema.json"
)

_MINIMAL_MANIFEST = """\
{
  "schema": "keeper-integrations-events.v1",
  "automator_endpoints": [
    {
      "uid_ref": "auto.hooks",
      "title": "Incident hooks",
      "endpoint_url": "https://hooks.acme.example.com/keeper"
    }
  ],
  "audit_alerts": [
    {
      "uid_ref": "alert.admins",
      "title": "Admin notifications",
      "template_id": "enterprise-alert-v1"
    }
  ],
  "api_keys": [
    {
      "uid_ref": "key.reporting",
      "title": "Reporting integration"
    }
  ]
}
"""

_FULL_MANIFEST = """\
{
  "schema": "keeper-integrations-events.v1",
  "automator_endpoints": [
    {
      "uid_ref": "auto.hooks",
      "title": "Incident hooks",
      "endpoint_url": "https://hooks.acme.example.com/keeper",
      "enabled": false,
      "event_kinds": ["record_add", "record_update"],
      "signing_secret_record_uid_ref": "keeper-vault:records:rec.signing"
    }
  ],
  "audit_alerts": [
    {
      "uid_ref": "alert.admins",
      "title": "Admin notifications",
      "template_id": "enterprise-alert-v1",
      "enabled": true
    }
  ],
  "api_keys": [
    {
      "uid_ref": "key.reporting",
      "title": "Reporting integration",
      "scopes": "reports:read",
      "material_record_uid_ref": "keeper-vault:records:rec.apikey",
      "ksm_app_uid_ref": "keeper-ksm:ksm_apps:app.reporting"
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
    for collection in ("automator_endpoints", "audit_alerts", "api_keys"):
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


def test_keeper_integrations_events_schema_accepts_minimal() -> None:
    _validate(_doc())


def test_keeper_integrations_events_schema_accepts_full() -> None:
    _validate(_doc(_FULL_MANIFEST))


def test_keeper_integrations_events_schema_rejects_bad_record_ref() -> None:
    document = _doc(_FULL_MANIFEST)
    document["automator_endpoints"][0]["signing_secret_record_uid_ref"] = "keeper-vault:nope:x"

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert "signing_secret" in exc.value.context["location"]


def test_keeper_integrations_events_schema_rejects_uid_ref_collision() -> None:
    document = _doc()
    document["api_keys"][0]["uid_ref"] = "auto.hooks"

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert "duplicate uid_ref" in exc.value.reason


def test_keeper_integrations_events_schema_rejects_short_endpoint_url() -> None:
    document = _doc()
    document["automator_endpoints"][0]["endpoint_url"] = "http://"

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert "endpoint_url" in exc.value.context["location"]
