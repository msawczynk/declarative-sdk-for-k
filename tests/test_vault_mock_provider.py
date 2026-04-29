"""Vault manifest + MockProvider: diff, plan, apply (PR-V3)."""

from __future__ import annotations

from keeper_sdk.core import (
    build_plan,
    compute_vault_diff,
    load_vault_manifest,
    vault_record_apply_order,
)
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.providers import MockProvider


def _minimal_vault_doc() -> dict:
    return {
        "schema": "keeper-vault.v1",
        "records": [
            {
                "uid_ref": "vault.login.alpha",
                "type": "login",
                "title": "Alpha",
                "fields": [{"type": "login", "label": "Login", "value": ["u"]}],
            }
        ],
    }


def _login_record(uid_ref: str, *, depends_on: str | None = None) -> dict:
    record = {
        "uid_ref": uid_ref,
        "type": "login",
        "title": uid_ref.rsplit(".", 1)[-1].title(),
        "fields": [{"type": "login", "label": "Login", "value": [f"{uid_ref}@example.com"]}],
    }
    if depends_on is not None:
        record["custom"] = [
            {
                "type": "text",
                "label": "Depends On",
                "value": [f"keeper-vault:records:{depends_on}"],
            }
        ]
    return record


def test_vault_apply_then_replan_is_clean() -> None:
    manifest = load_vault_manifest(_minimal_vault_doc())
    name = "fixture-stem"
    provider = MockProvider(name)
    order = vault_record_apply_order(manifest)

    changes = compute_vault_diff(manifest, provider.discover(), manifest_name=name)
    plan = build_plan(name, changes, order)
    outcomes = provider.apply_plan(plan)
    assert any(o.action == "create" for o in outcomes)

    changes2 = compute_vault_diff(manifest, provider.discover(), manifest_name=name)
    assert [c for c in changes2 if c.kind is ChangeKind.CREATE] == []


def test_vault_allow_delete_orphan() -> None:
    manifest = load_vault_manifest(_minimal_vault_doc())
    name = "fixture-stem"
    provider = MockProvider(name)
    order = vault_record_apply_order(manifest)

    provider.apply_plan(
        build_plan(
            name,
            compute_vault_diff(manifest, provider.discover(), manifest_name=name),
            order,
        )
    )
    provider.seed_payload(
        title="Orphan",
        resource_type="login",
        payload={"title": "Orphan"},
        marker_uid_ref="orphan-ref",
        manifest_name=name,
    )

    changes = compute_vault_diff(
        manifest, provider.discover(), manifest_name=name, allow_delete=True
    )
    deletes = [c for c in changes if c.kind is ChangeKind.DELETE]
    assert any(c.title == "Orphan" for c in deletes)

    plan2 = build_plan(name, changes, order)
    outcomes = provider.apply_plan(plan2)
    assert any(o.action == "delete" for o in outcomes)


def test_vault_multi_record_apply_order() -> None:
    doc = {
        "schema": "keeper-vault.v1",
        "records": [
            _login_record("vault.login.a"),
            _login_record("vault.login.b", depends_on="vault.login.a"),
            _login_record("vault.login.c", depends_on="vault.login.b"),
        ],
    }
    manifest = load_vault_manifest(doc)
    name = "ordering-fixture"
    provider = MockProvider(name)

    order = vault_record_apply_order(manifest)
    assert order == ["vault.login.a", "vault.login.b", "vault.login.c"]

    changes = compute_vault_diff(manifest, provider.discover(), manifest_name=name)
    outcomes = provider.apply_plan(build_plan(name, changes, order))

    assert [outcome.uid_ref for outcome in outcomes] == order
    assert [record.marker["uid_ref"] for record in provider.discover()] == order
