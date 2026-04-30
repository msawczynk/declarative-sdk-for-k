"""keeper-vault.v1 broader typed fields and file-ref stubs."""

from __future__ import annotations

import json
from typing import Any

import pytest

from keeper_sdk.cli.main import _plan_to_dict
from keeper_sdk.core import build_plan, compute_vault_diff, load_vault_manifest
from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.core.redact import REDACTED
from keeper_sdk.core.vault_graph import vault_record_apply_order


def _record(
    *,
    fields: list[dict[str, Any]] | None = None,
    custom: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "uid_ref": "vault.login.alpha",
        "type": "login",
        "title": "Alpha",
        "fields": fields if fields is not None else [_field("login", "Login", "alpha-user")],
    }
    if custom is not None:
        row["custom"] = custom
    return row


def _doc(
    *,
    fields: list[dict[str, Any]] | None = None,
    custom: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {"schema": "keeper-vault.v1", "records": [_record(fields=fields, custom=custom)]}


def _field(field_type: str, label: str, value: Any) -> dict[str, Any]:
    return {"type": field_type, "label": label, "value": [value]}


def _file_ref_field(name: str = "runbook.pdf") -> dict[str, Any]:
    return _field(
        "file_ref",
        "Runbook",
        {
            "uid_ref": "att.runbook",
            "keeper_uid": "FILE_UID_123",
            "name": name,
            "mime_type": "application/pdf",
            "content_sha256": "a" * 64,
        },
    )


def _marker() -> dict[str, str]:
    return encode_marker(
        uid_ref="vault.login.alpha",
        manifest="demo",
        resource_type="login",
    )


def _live(
    *,
    fields: list[dict[str, Any]] | None = None,
    custom: list[dict[str, Any]] | None = None,
    payload_extra: dict[str, Any] | None = None,
) -> LiveRecord:
    payload: dict[str, Any] = {"type": "login", "title": "Alpha"}
    if fields is not None:
        payload["fields"] = fields
    if custom is not None:
        payload["custom"] = custom
    if payload_extra:
        payload.update(payload_extra)
    return LiveRecord(
        keeper_uid="uid-alpha",
        title="Alpha",
        resource_type="login",
        payload=payload,
        marker=_marker(),
    )


def _single_update(
    desired_doc: dict[str, Any],
    live: LiveRecord,
) -> Change:
    manifest = load_vault_manifest(desired_doc)
    rows = compute_vault_diff(manifest, [live], manifest_name="demo")
    updates = [row for row in rows if row.kind is ChangeKind.UPDATE]
    assert len(updates) == 1
    return updates[0]


def test_validate_manifest_accepts_url_email_phone_fields() -> None:
    manifest = load_vault_manifest(
        _doc(
            fields=[
                _field("login", "Login", "alpha-user"),
                _field("url", "URL", "https://example.invalid"),
                _field("email", "Email", "owner@example.invalid"),
                _field("phone", "Phone", "+15550100"),
            ]
        )
    )

    assert [field["type"] for field in manifest.records[0].fields] == [
        "login",
        "url",
        "email",
        "phone",
    ]


def test_validate_manifest_accepts_address_secret_question_multiline_fields() -> None:
    manifest = load_vault_manifest(
        _doc(
            fields=[
                _field("address", "Address", "1 Main St"),
                _field("secret_question", "Recovery", "first city?"),
                _field("multiline", "Notes", "line 1\nline 2"),
            ]
        )
    )

    assert [field["type"] for field in manifest.records[0].fields] == [
        "address",
        "secret_question",
        "multiline",
    ]


def test_validate_manifest_accepts_structured_phone_and_address_values() -> None:
    manifest = load_vault_manifest(
        _doc(
            fields=[
                _field("phone", "Support Phone", {"region": "US", "number": "5550100"}),
                _field("address", "HQ", {"city": "London", "country": "GB"}),
            ]
        )
    )

    assert manifest.records[0].fields[0]["value"][0]["number"] == "5550100"


def test_diff_detects_url_change() -> None:
    before = [_field("login", "Login", "alpha-user"), _field("url", "URL", "https://old")]
    after = [_field("login", "Login", "alpha-user"), _field("url", "URL", "https://new")]

    row = _single_update(_doc(fields=after), _live(fields=before))

    assert row.before == {"fields": before}
    assert row.after == {"fields": after}


def test_diff_detects_email_add() -> None:
    before = [_field("login", "Login", "alpha-user")]
    after = [_field("login", "Login", "alpha-user"), _field("email", "Email", "a@example.invalid")]

    row = _single_update(_doc(fields=after), _live(fields=before))

    assert row.before == {"fields": before}
    assert row.after == {"fields": after}


def test_diff_detects_field_type_mismatch_with_same_label_and_value() -> None:
    live_fields = [_field("url", "Contact", "owner@example.invalid")]
    desired_fields = [_field("email", "Contact", "owner@example.invalid")]

    row = _single_update(_doc(fields=desired_fields), _live(fields=live_fields))

    assert row.before == {"fields": live_fields}
    assert row.after == {"fields": desired_fields}


def test_diff_keeps_flattened_scalar_live_payload_clean() -> None:
    fields = [
        _field("login", "Login", "alpha-user"),
        _field("url", "URL", "https://example.invalid"),
        _field("email", "Email", "owner@example.invalid"),
        _field("phone", "Phone", "+15550100"),
    ]
    manifest = load_vault_manifest(_doc(fields=fields))
    rows = compute_vault_diff(
        manifest,
        [
            _live(
                payload_extra={
                    "Login": "alpha-user",
                    "URL": "https://example.invalid",
                    "Email": "owner@example.invalid",
                    "Phone": "+15550100",
                }
            )
        ],
        manifest_name="demo",
    )

    assert [row.kind for row in rows] == [ChangeKind.NOOP]


def test_diff_updates_when_structured_field_has_no_live_typed_fields() -> None:
    fields = [_field("address", "HQ", {"city": "London", "country": "GB"})]

    row = _single_update(_doc(fields=fields), _live(payload_extra={"HQ": "London"}))

    assert row.after == {"fields": fields}


def test_file_ref_fields_are_redacted_in_plan_json() -> None:
    manifest = load_vault_manifest(
        _doc(fields=[_field("login", "Login", "alpha-user"), _file_ref_field()])
    )
    changes = compute_vault_diff(manifest, [], manifest_name="demo")
    plan = build_plan("demo", changes, vault_record_apply_order(manifest))

    rendered = _plan_to_dict(plan)

    field = rendered["changes"][0]["after"]["fields"][1]
    assert field["type"] == "file_ref"
    assert field["value"] == [REDACTED]
    assert "FILE_UID_123" not in json.dumps(rendered)


def test_file_ref_field_change_is_detected_before_redaction() -> None:
    live_fields = [_field("login", "Login", "alpha-user"), _file_ref_field("old.pdf")]
    desired_fields = [_field("login", "Login", "alpha-user"), _file_ref_field("new.pdf")]

    row = _single_update(_doc(fields=desired_fields), _live(fields=live_fields))

    assert row.before == {"fields": live_fields}
    assert row.after == {"fields": desired_fields}


def test_custom_key_value_add_is_detected() -> None:
    custom = [{"key": "owner", "value": "platform"}]

    row = _single_update(
        _doc(custom=custom),
        _live(fields=[_field("login", "Login", "alpha-user")], custom=[]),
    )

    assert row.before == {"custom": []}
    assert row.after == {"custom": custom}


def test_custom_key_value_remove_is_detected() -> None:
    custom = [{"key": "owner", "value": "platform"}]

    row = _single_update(
        _doc(custom=[]),
        _live(fields=[_field("login", "Login", "alpha-user")], custom=custom),
    )

    assert row.before == {"custom": custom}
    assert row.after == {"custom": []}


def test_custom_key_value_change_is_detected() -> None:
    before = [{"key": "owner", "value": "platform"}]
    after = [{"key": "owner", "value": "security"}]

    row = _single_update(
        _doc(custom=after),
        _live(fields=[_field("login", "Login", "alpha-user")], custom=before),
    )

    assert row.before == {"custom": before}
    assert row.after == {"custom": after}


def test_invalid_field_type_is_rejected() -> None:
    with pytest.raises(SchemaError, match="not one of"):
        load_vault_manifest(_doc(fields=[_field("not_a_keeper_field", "Bad", "x")]))
