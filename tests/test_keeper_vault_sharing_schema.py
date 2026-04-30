"""keeper-vault-sharing.v1 JSON Schema contract tests."""

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
    / "keeper-vault-sharing"
    / "keeper-vault-sharing.v1.schema.json"
)
_V9A_EVIDENCE = "docs/live-proof/keeper-vault-sharing.v1.535e03f.folderlifecycle.sanitized.json"

_MINIMAL_MANIFEST = """\
{
  "schema": "keeper-vault-sharing.v1",
  "share_records": [
    {
      "uid_ref": "share.web-admin.platform",
      "record_uid_ref": "keeper-vault:records:rec.web-admin",
      "user_email": "platform@example.com",
      "permissions": {
        "can_edit": false,
        "can_share": false
      }
    }
  ]
}
"""

_FULL_MANIFEST = """\
{
  "schema": "keeper-vault-sharing.v1",
  "folders": [
    {
      "uid_ref": "folder.prod",
      "path": "/Prod",
      "color": "blue"
    },
    {
      "uid_ref": "folder.prod.web",
      "path": "/Prod/Web",
      "parent_folder_uid_ref": "keeper-vault-sharing:folders:folder.prod",
      "color": "green"
    }
  ],
  "shared_folders": [
    {
      "uid_ref": "sf.prod",
      "path": "/Shared/Prod",
      "defaults": {
        "manage_users": false,
        "manage_records": true,
        "can_edit": true,
        "can_share": false
      }
    }
  ],
  "share_records": [
    {
      "uid_ref": "share.web-admin.platform",
      "record_uid_ref": "keeper-vault:records:rec.web-admin",
      "user_email": "platform@example.com",
      "permissions": {
        "can_edit": true,
        "can_share": false
      },
      "expires_at": "2026-12-31T23:59:59Z"
    }
  ],
  "share_folders": [
    {
      "kind": "grantee",
      "uid_ref": "sf.prod.user.platform",
      "shared_folder_uid_ref": "keeper-vault-sharing:shared_folders:sf.prod",
      "grantee": {
        "kind": "user",
        "user_email": "platform@example.com"
      },
      "permissions": {
        "manage_records": true,
        "manage_users": false
      },
      "expires_at": "2026-12-31T23:59:59Z"
    },
    {
      "kind": "grantee",
      "uid_ref": "sf.prod.team.ops",
      "shared_folder_uid_ref": "keeper-vault-sharing:shared_folders:sf.prod",
      "grantee": {
        "kind": "team",
        "team_uid_ref": "keeper-enterprise:teams:team.ops"
      },
      "permissions": {
        "manage_records": false,
        "manage_users": false
      }
    },
    {
      "kind": "record",
      "uid_ref": "sf.prod.record.web-admin",
      "shared_folder_uid_ref": "keeper-vault-sharing:shared_folders:sf.prod",
      "record_uid_ref": "keeper-vault:records:rec.web-admin",
      "permissions": {
        "can_edit": true,
        "can_share": false
      },
      "expires_at": "2026-12-31T23:59:59Z"
    },
    {
      "kind": "default",
      "uid_ref": "sf.prod.default.grantee",
      "shared_folder_uid_ref": "keeper-vault-sharing:shared_folders:sf.prod",
      "target": "grantee",
      "permissions": {
        "manage_records": true,
        "manage_users": false
      }
    },
    {
      "kind": "default",
      "uid_ref": "sf.prod.default.record",
      "shared_folder_uid_ref": "keeper-vault-sharing:shared_folders:sf.prod",
      "target": "record",
      "permissions": {
        "can_edit": true,
        "can_share": false
      }
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
    for collection in ("folders", "shared_folders", "share_records", "share_folders"):
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


def test_keeper_vault_sharing_schema_accepts_valid_minimal_manifest() -> None:
    _validate(_doc())


def test_keeper_vault_sharing_schema_accepts_valid_full_manifest() -> None:
    _validate(_doc(_FULL_MANIFEST))


@pytest.mark.parametrize("field", ["uid_ref", "record_uid_ref", "user_email", "permissions"])
def test_keeper_vault_sharing_schema_rejects_missing_required_record_share_field(
    field: str,
) -> None:
    document = _doc()
    del document["share_records"][0][field]

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert field in exc.value.reason
    assert exc.value.context["location"] == "share_records/0"


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ((), "unexpected"),
        (("folders", 0), "unexpected"),
        (("shared_folders", 0), "unexpected"),
        (("shared_folders", 0, "defaults"), "unexpected"),
        (("share_records", 0), "unexpected"),
        (("share_records", 0, "permissions"), "unexpected"),
        (("share_folders", 0), "unexpected"),
        (("share_folders", 0, "grantee"), "unexpected"),
        (("share_folders", 0, "permissions"), "unexpected"),
    ],
)
def test_keeper_vault_sharing_schema_rejects_unknown_properties(
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


def test_keeper_vault_sharing_schema_validates_cross_family_reference_shapes() -> None:
    valid = _doc(_FULL_MANIFEST)
    _validate(valid)

    valid_record_ref = copy.deepcopy(valid)
    valid_record_ref["share_records"][0]["record_uid_ref"] = "keeper-vault:records:rec.api_1"
    _validate(valid_record_ref)

    valid_team_ref = copy.deepcopy(valid)
    valid_team_ref["share_folders"][1]["grantee"]["team_uid_ref"] = (
        "keeper-enterprise:teams:team.api_1"
    )
    _validate(valid_team_ref)

    invalid_self_ref = copy.deepcopy(valid)
    invalid_self_ref["share_records"][0]["record_uid_ref"] = "keeper-vault-sharing:foo:bar"

    with pytest.raises(SchemaError) as exc:
        _validate(invalid_self_ref)

    assert exc.value.context["location"] == "share_records/0/record_uid_ref"


def test_keeper_vault_sharing_schema_rejects_uid_ref_collisions() -> None:
    document = _doc(_FULL_MANIFEST)
    document["share_folders"][0]["uid_ref"] = "sf.prod"

    with pytest.raises(SchemaError) as exc:
        _validate(document)

    assert "duplicate uid_ref" in exc.value.reason
    assert "sf.prod" in exc.value.reason


def test_keeper_vault_sharing_live_proof_evidence_points_to_v9a_transcript() -> None:
    live_proof = _schema()["x-keeper-live-proof"]

    assert live_proof["status"] == "scaffold-only"
    assert live_proof["evidence"] == [_V9A_EVIDENCE]
    assert "awaiting V9b record share lifecycle" in live_proof["notes"]


def test_keeper_vault_sharing_v9a_evidence_file_is_committed_json() -> None:
    evidence_path = Path(__file__).resolve().parents[1] / _V9A_EVIDENCE

    payload = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert payload["family"] == "keeper-vault-sharing.v1"
    assert payload["scenario"] == "folderlifecycle"
    assert [event["exit_code"] for event in payload["events"]] == [0, 2, 0, 0, 0, 2, 0, 0]
