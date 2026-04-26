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
    / "keeper-pam-extended"
    / "keeper-pam-extended.v1.schema.json"
)

_MINIMAL_MANIFEST = """\
{
  "schema": "keeper-pam-extended.v1",
  "gateway_configs": [
    {
      "uid_ref": "gwcfg.edge",
      "title": "Edge pool",
      "ksm_application_name": "pam-edge"
    }
  ],
  "rotation_schedules": [
    {
      "uid_ref": "rot.db-hourly",
      "schedule": { "type": "on-demand" },
      "record_refs": ["keeper-vault:records:rec.db-admin"]
    }
  ],
  "discovery_rules": [
    {
      "uid_ref": "disc.internal-cidr",
      "title": "Internal CIDR",
      "match_kind": "ip_cidr",
      "match_value": "10.0.0.0/8"
    }
  ]
}
"""

_FULL_MANIFEST = """\
{
  "schema": "keeper-pam-extended.v1",
  "gateway_configs": [
    {
      "uid_ref": "gwcfg.edge",
      "title": "Edge pool",
      "ksm_application_name": "pam-edge",
      "enterprise_node_uid_ref": "keeper-enterprise:nodes:node.edge",
      "ksm_app_uid_ref": "keeper-ksm:ksm_apps:app.edge",
      "notes": "cross-project"
    }
  ],
  "rotation_schedules": [
    {
      "uid_ref": "rot.db-hourly",
      "title": "DB rotation",
      "schedule": { "type": "CRON", "cron": "0 * * * *" },
      "record_refs": [
        "keeper-vault:records:rec.db-admin",
        "keeper-vault:records:rec.db-readonly"
      ]
    }
  ],
  "discovery_rules": [
    {
      "uid_ref": "disc.web-hosts",
      "title": "Web tier",
      "match_kind": "hostname_regex",
      "match_value": "^web\\\\d+\\\\.example\\\\.com$",
      "enterprise_node_uid_ref": "keeper-enterprise:nodes:node.platform",
      "notes": "feeds vault adoption"
    }
  ]
}
"""

_STUB_COLLECTIONS = ("service_mappings", "saas_mappings")


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
    for collection in ("gateway_configs", "rotation_schedules", "discovery_rules"):
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


def test_keeper_pam_extended_schema_accepts_valid_minimal_manifest() -> None:
    _validate(_doc())


def test_keeper_pam_extended_schema_accepts_valid_full_manifest() -> None:
    _validate(_doc(_FULL_MANIFEST))


@pytest.mark.parametrize(
    ("collection", "field"),
    [
        ("gateway_configs", "uid_ref"),
        ("gateway_configs", "title"),
        ("gateway_configs", "ksm_application_name"),
        ("rotation_schedules", "uid_ref"),
        ("rotation_schedules", "schedule"),
        ("discovery_rules", "uid_ref"),
        ("discovery_rules", "title"),
        ("discovery_rules", "match_kind"),
        ("discovery_rules", "match_value"),
    ],
)
def test_keeper_pam_extended_schema_rejects_missing_required_field(
    collection: str, field: str
) -> None:
    document = _doc()
    del document[collection][0][field]

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert field in exc.value.reason
    assert exc.value.context["location"].startswith(f"{collection}/0")


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ((), "unexpected"),
        (("gateway_configs", 0), "unexpected"),
        (("rotation_schedules", 0), "unexpected"),
        (("discovery_rules", 0), "unexpected"),
    ],
)
def test_keeper_pam_extended_schema_rejects_unknown_properties(
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


def test_keeper_pam_extended_schema_rejects_uid_ref_collisions() -> None:
    document = _doc(_FULL_MANIFEST)
    document["discovery_rules"][0]["uid_ref"] = "gwcfg.edge"

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert "duplicate uid_ref" in exc.value.reason
    assert "gwcfg.edge" in exc.value.reason


def test_keeper_pam_extended_schema_rejects_bad_record_ref_pattern() -> None:
    document = _doc()
    document["rotation_schedules"][0]["record_refs"] = ["keeper-vault:records:/bad"]

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert "record_refs" in exc.value.context["location"]


def test_keeper_pam_extended_schema_rejects_short_cron() -> None:
    document = _doc()
    document["rotation_schedules"][0]["schedule"] = {"type": "CRON", "cron": "0 * * *"}

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert exc.value.context["location"].startswith("rotation_schedules/0/schedule")


def test_keeper_pam_extended_schema_accepts_empty_scaffold_stub_blocks() -> None:
    document = _doc()
    for collection in _STUB_COLLECTIONS:
        document[collection] = []

    _validate(document)


@pytest.mark.parametrize("collection", _STUB_COLLECTIONS)
def test_keeper_pam_extended_schema_rejects_non_empty_scaffold_stub_blocks(
    collection: str,
) -> None:
    document = _doc()
    document[collection] = [{}]

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert exc.value.context["location"] == collection
