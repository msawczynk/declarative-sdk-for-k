"""keeper-vault.v1 semantic diff (Commander flattening vs manifest fields[])."""

from __future__ import annotations

from keeper_sdk.core import compute_vault_diff, load_vault_manifest
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import MARKER_FIELD_LABEL, encode_marker, serialize_marker


def _manifest_one_login() -> dict:
    return {
        "schema": "keeper-vault.v1",
        "records": [
            {
                "uid_ref": "vault.login.alpha",
                "type": "login",
                "title": "Alpha",
                "fields": [{"type": "login", "label": "Login", "value": ["user1"]}],
            }
        ],
    }


def _field_manifest(fields: list[dict[str, object]]) -> dict:
    return {
        "schema": "keeper-vault.v1",
        "records": [
            {
                "uid_ref": "vault.login.alpha",
                "type": "login",
                "title": "Alpha",
                "fields": fields,
            }
        ],
    }


def _login_field(value: str = "user1") -> dict[str, object]:
    return {"type": "login", "label": "Login", "value": [value]}


def _password_field(value: str) -> dict[str, object]:
    return {"type": "password", "label": "Password", "value": [value]}


def _marked_live_with_fields(fields: list[dict[str, object]]) -> LiveRecord:
    marker = encode_marker(
        uid_ref="vault.login.alpha",
        manifest="demo",
        resource_type="login",
    )
    return LiveRecord(
        keeper_uid="uid-1",
        title="Alpha",
        resource_type="login",
        payload={"type": "login", "title": "Alpha", "fields": fields},
        marker=marker,
    )


def _single_update_for_fields(
    desired_fields: list[dict[str, object]],
    live_fields: list[dict[str, object]],
):
    manifest = load_vault_manifest(_field_manifest(desired_fields))
    changes = compute_vault_diff(
        manifest,
        [_marked_live_with_fields(live_fields)],
        manifest_name="demo",
    )
    updates = [change for change in changes if change.kind is ChangeKind.UPDATE]
    assert len(updates) == 1
    return updates[0]


def test_vault_diff_noop_when_live_flattens_fields() -> None:
    """Commander-style payload: no ``fields[]``, scalars lifted to top-level keys."""
    manifest = load_vault_manifest(_manifest_one_login())
    marker = encode_marker(
        uid_ref="vault.login.alpha",
        manifest="demo",
        resource_type="login",
    )
    live = LiveRecord(
        keeper_uid="uid-1",
        title="Alpha",
        resource_type="login",
        payload={
            "type": "login",
            "title": "Alpha",
            "Login": "user1",
        },
        marker=marker,
    )
    changes = compute_vault_diff(manifest, [live], manifest_name="demo")
    kinds = [c.kind for c in changes if c.uid_ref == "vault.login.alpha"]
    assert kinds == [ChangeKind.NOOP]


def test_vault_diff_update_when_flattened_login_differs() -> None:
    manifest = load_vault_manifest(_manifest_one_login())
    marker = encode_marker(
        uid_ref="vault.login.alpha",
        manifest="demo",
        resource_type="login",
    )
    live = LiveRecord(
        keeper_uid="uid-1",
        title="Alpha",
        resource_type="login",
        payload={"type": "login", "title": "Alpha", "Login": "other-user"},
        marker=marker,
    )
    changes = compute_vault_diff(manifest, [live], manifest_name="demo")
    row = next(c for c in changes if c.uid_ref == "vault.login.alpha")
    assert row.kind is ChangeKind.UPDATE
    assert "fields" in (row.after or {})


def test_vault_diff_case_insensitive_field_labels() -> None:
    """Flattened live keys may differ only by case from manifest ``fields[].label``."""
    doc = {
        "schema": "keeper-vault.v1",
        "records": [
            {
                "uid_ref": "vault.login.gamma",
                "type": "login",
                "title": "G",
                "fields": [
                    {"type": "password", "label": "password", "value": ["s3cr3t"]},
                ],
            }
        ],
    }
    manifest = load_vault_manifest(doc)
    marker = encode_marker(uid_ref="vault.login.gamma", manifest="demo", resource_type="login")
    live = LiveRecord(
        keeper_uid="uid-3",
        title="G",
        resource_type="login",
        payload={"type": "login", "title": "G", "Password": "s3cr3t"},
        marker=marker,
    )
    changes = compute_vault_diff(manifest, [live], manifest_name="demo")
    kinds = [c.kind for c in changes if c.uid_ref == "vault.login.gamma"]
    assert kinds == [ChangeKind.NOOP]


def test_vault_diff_custom_ignores_marker_mismatch() -> None:
    doc = {
        "schema": "keeper-vault.v1",
        "records": [
            {
                "uid_ref": "vault.login.beta",
                "type": "login",
                "title": "B",
                "fields": [],
                "custom": [{"type": "text", "label": "note", "value": ["x"]}],
            }
        ],
    }
    manifest = load_vault_manifest(doc)
    marker = encode_marker(uid_ref="vault.login.beta", manifest="demo", resource_type="login")

    live = LiveRecord(
        keeper_uid="uid-2",
        title="B",
        resource_type="login",
        payload={
            "type": "login",
            "title": "B",
            "custom": [
                {"type": "text", "label": "note", "value": ["x"]},
                {
                    "type": "text",
                    "label": MARKER_FIELD_LABEL,
                    "value": [serialize_marker(marker)],
                },
            ],
        },
        marker=marker,
    )
    changes = compute_vault_diff(manifest, [live], manifest_name="demo")
    kinds = [c.kind for c in changes if c.uid_ref == "vault.login.beta"]
    assert kinds == [ChangeKind.NOOP]


def test_vault_diff_update_when_password_field_value_changes() -> None:
    before_fields = [_login_field(), _password_field("old-secret")]
    after_fields = [_login_field(), _password_field("new-secret")]

    row = _single_update_for_fields(after_fields, before_fields)

    assert row.before == {"fields": before_fields}
    assert row.after == {"fields": after_fields}


def test_vault_diff_update_when_password_field_is_added() -> None:
    before_fields = [_login_field()]
    after_fields = [_login_field(), _password_field("new-secret")]

    row = _single_update_for_fields(after_fields, before_fields)

    assert row.before == {"fields": before_fields}
    assert row.after == {"fields": after_fields}


def test_vault_diff_update_when_password_field_is_removed() -> None:
    before_fields = [_login_field(), _password_field("old-secret")]
    after_fields = [_login_field()]

    row = _single_update_for_fields(after_fields, before_fields)

    assert row.before == {"fields": before_fields}
    assert row.after == {"fields": after_fields}
