"""keeper-vault.v1 custom field diff coverage."""

from __future__ import annotations

from typing import Any

from keeper_sdk.core import (
    build_plan,
    compute_vault_diff,
    load_vault_manifest,
    vault_record_apply_order,
)
from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.providers import MockProvider


def _custom(label: str, value: str) -> dict[str, Any]:
    return {"type": "secret", "label": label, "value": [value]}


def _vault_doc(custom: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "uid_ref": "vault.login.alpha",
        "type": "login",
        "title": "Alpha",
        "fields": [{"type": "login", "label": "Login", "value": ["alpha-user"]}],
    }
    if custom is not None:
        record["custom"] = custom
    return {"schema": "keeper-vault.v1", "records": [record]}


def _provider_after_apply(doc: dict[str, Any], *, name: str = "custom-fields") -> MockProvider:
    manifest = load_vault_manifest(doc)
    provider = MockProvider(name)
    changes = compute_vault_diff(manifest, provider.discover(), manifest_name=name)
    plan = build_plan(name, changes, vault_record_apply_order(manifest))
    outcomes = provider.apply_plan(plan)
    assert [outcome.action for outcome in outcomes] == ["create"]
    return provider


def _single_update(before_doc: dict[str, Any], after_doc: dict[str, Any]) -> Change:
    name = "custom-fields"
    provider = _provider_after_apply(before_doc, name=name)
    manifest = load_vault_manifest(after_doc)
    updates = [
        change
        for change in compute_vault_diff(manifest, provider.discover(), manifest_name=name)
        if change.kind is ChangeKind.UPDATE
    ]
    assert len(updates) == 1
    return updates[0]


def test_manifest_with_custom_field_validates_ok() -> None:
    manifest = load_vault_manifest(_vault_doc([_custom("API Key", "old-key")]))

    assert manifest.records[0].custom == [_custom("API Key", "old-key")]


def test_custom_field_value_change_is_update() -> None:
    update = _single_update(
        _vault_doc([_custom("API Key", "old-key")]),
        _vault_doc([_custom("API Key", "new-key")]),
    )

    assert update.before["custom"] == [_custom("API Key", "old-key")]
    assert update.after["custom"] == [_custom("API Key", "new-key")]


def test_custom_field_added_is_update() -> None:
    update = _single_update(_vault_doc(), _vault_doc([_custom("API Key", "new-key")]))

    assert update.before["custom"] == []
    assert update.after["custom"] == [_custom("API Key", "new-key")]


def test_custom_field_removed_is_update() -> None:
    update = _single_update(_vault_doc([_custom("API Key", "old-key")]), _vault_doc())

    assert update.before["custom"] == [_custom("API Key", "old-key")]
    assert update.after["custom"] == []


def test_duplicate_custom_labels_are_currently_schema_valid() -> None:
    # rules.py rejects duplicate labels in records[].fields, not records[].custom.
    manifest = load_vault_manifest(
        _vault_doc([_custom("API Key", "old-key"), _custom("API Key", "new-key")])
    )

    assert [field["label"] for field in manifest.records[0].custom] == ["API Key", "API Key"]
