"""Offline smoke for keeper-vault.v1 login field updates."""

from __future__ import annotations

from keeper_sdk.core import (
    build_plan,
    compute_vault_diff,
    load_vault_manifest,
    vault_record_apply_order,
)
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.providers import MockProvider

MANIFEST_NAME = "vault-update-smoke"
UID_REF = "vault.login.update"


def _fields(password: str) -> list[dict[str, object]]:
    return [
        {"type": "login", "label": "Login", "value": ["user@example.invalid"]},
        {"type": "password", "label": "Password", "value": [password]},
    ]


def _vault_doc(password: str) -> dict[str, object]:
    return {
        "schema": "keeper-vault.v1",
        "records": [
            {
                "uid_ref": UID_REF,
                "type": "login",
                "title": "Update Smoke Login",
                "fields": _fields(password),
            }
        ],
    }


def test_vault_login_password_update_apply_converge_destroy() -> None:
    initial = load_vault_manifest(_vault_doc("initial-secret"))
    provider = MockProvider(MANIFEST_NAME)
    order = vault_record_apply_order(initial)

    create_changes = compute_vault_diff(initial, provider.discover(), manifest_name=MANIFEST_NAME)
    assert [change.kind for change in create_changes] == [ChangeKind.CREATE]
    create_outcomes = provider.apply_plan(build_plan(MANIFEST_NAME, create_changes, order))
    assert [outcome.action for outcome in create_outcomes] == ["create"]

    updated = load_vault_manifest(_vault_doc("rotated-secret"))
    update_changes = compute_vault_diff(updated, provider.discover(), manifest_name=MANIFEST_NAME)
    updates = [change for change in update_changes if change.kind is ChangeKind.UPDATE]
    assert len(updates) == 1
    assert updates[0].uid_ref == UID_REF
    assert updates[0].before == {"fields": _fields("initial-secret")}
    assert updates[0].after == {"fields": _fields("rotated-secret")}

    update_outcomes = provider.apply_plan(build_plan(MANIFEST_NAME, updates, order))
    assert [outcome.action for outcome in update_outcomes] == ["update"]

    converged = compute_vault_diff(updated, provider.discover(), manifest_name=MANIFEST_NAME)
    assert [change for change in converged if change.kind is not ChangeKind.NOOP] == []

    empty = load_vault_manifest({"schema": "keeper-vault.v1", "records": []})
    destroy_changes = compute_vault_diff(
        empty,
        provider.discover(),
        manifest_name=MANIFEST_NAME,
        allow_delete=True,
    )
    deletes = [change for change in destroy_changes if change.kind is ChangeKind.DELETE]
    assert len(deletes) == 1
    assert deletes[0].uid_ref == UID_REF

    destroy_outcomes = provider.apply_plan(build_plan(MANIFEST_NAME, destroy_changes, []))
    assert [outcome.action for outcome in destroy_outcomes] == ["delete"]
    assert provider.discover() == []
