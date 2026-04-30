"""MockProvider MSP managed-company apply tests (P4 slice 1)."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.msp_diff import compute_msp_diff
from keeper_sdk.core.msp_graph import msp_apply_order
from keeper_sdk.core.msp_models import MspManifestV1, load_msp_manifest
from keeper_sdk.core.planner import Plan, build_plan
from keeper_sdk.providers import MockProvider
from keeper_sdk.providers.commander_cli import CommanderCliProvider, ConflictError


def _manifest(*managed_companies: dict[str, Any]) -> MspManifestV1:
    return load_msp_manifest(
        {
            "schema": "msp-environment.v1",
            "name": "msp-mock-test",
            "managed_companies": list(managed_companies),
        }
    )


def _mc(
    name: str,
    *,
    plan: str = "business",
    seats: int = 5,
    file_plan: str | None = None,
    addons: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"name": name, "plan": plan, "seats": seats}
    if file_plan is not None:
        row["file_plan"] = file_plan
    if addons is not None:
        row["addons"] = addons
    return row


def _plan(
    manifest: MspManifestV1,
    provider: MockProvider,
    *,
    allow_delete: bool = False,
) -> Plan:
    return build_plan(
        manifest.name,
        compute_msp_diff(
            manifest,
            provider.discover_managed_companies(),
            allow_delete=allow_delete,
        ),
        msp_apply_order(manifest),
    )


def _custom_plan(*changes: Change, allow_delete: bool = True) -> Plan:
    plan = build_plan("msp-mock-test", list(changes), [change.uid_ref or "" for change in changes])
    setattr(plan, "allow_delete", allow_delete)
    return plan


def test_empty_manifest_and_empty_live_apply_returns_no_changes() -> None:
    provider = MockProvider()

    assert provider.apply_msp_plan(_plan(_manifest(), provider)) == []


def test_create_one_mc_round_trips_to_noop() -> None:
    provider = MockProvider()
    manifest = _manifest(_mc("Acme"))

    outcomes = provider.apply_msp_plan(_plan(manifest, provider))

    assert [outcome.action for outcome in outcomes] == ["create"]
    assert outcomes[0].uid_ref == "Acme"
    assert (
        compute_msp_diff(manifest, provider.discover_managed_companies())[0].kind is ChangeKind.NOOP
    )


def test_reapply_after_create_is_noop_and_state_stable() -> None:
    provider = MockProvider()
    manifest = _manifest(_mc("Acme"))
    provider.apply_msp_plan(_plan(manifest, provider))
    before = provider.discover_managed_companies()

    outcomes = provider.apply_msp_plan(_plan(manifest, provider))

    assert [outcome.action for outcome in outcomes] == ["noop"]
    assert provider.discover_managed_companies() == before


def test_dry_run_create_returns_outcome_without_changing_discover() -> None:
    provider = MockProvider()
    manifest = _manifest(_mc("Acme"))

    outcomes = provider.apply_msp_plan(_plan(manifest, provider), dry_run=True)

    assert [outcome.action for outcome in outcomes] == ["create"]
    assert provider.discover_managed_companies() == []


def test_update_seeded_mc_then_round_trips_to_noop() -> None:
    provider = MockProvider()
    provider.seed_managed_companies([_mc("Acme", seats=5)])
    manifest = _manifest(_mc("Acme", seats=9))

    outcomes = provider.apply_msp_plan(_plan(manifest, provider))

    assert [outcome.action for outcome in outcomes] == ["update"]
    assert (
        compute_msp_diff(manifest, provider.discover_managed_companies())[0].kind is ChangeKind.NOOP
    )


def test_delete_seeded_mc_with_allow_delete_removes_row() -> None:
    provider = MockProvider()
    provider.seed_managed_companies([_mc("Old")])

    outcomes = provider.apply_msp_plan(_plan(_manifest(), provider, allow_delete=True))

    assert [outcome.action for outcome in outcomes] == ["delete"]
    assert provider.discover_managed_companies() == []


def test_skip_without_allow_delete_is_noop_and_keeps_row() -> None:
    provider = MockProvider()
    provider.seed_managed_companies([_mc("Old")])

    outcomes = provider.apply_msp_plan(_plan(_manifest(), provider))

    assert [outcome.action for outcome in outcomes] == ["noop"]
    assert (
        outcomes[0].details["reason"]
        == "unmanaged managed_company; pass allow_delete=True to remove"
    )
    assert provider.discover_managed_companies()[0]["name"] == "Old"


def test_conflict_outcome_carries_reason() -> None:
    change = Change(
        kind=ChangeKind.CONFLICT,
        uid_ref="Acme",
        resource_type="managed_company",
        title="Acme",
        reason="duplicate live managed_company name: Acme",
    )

    outcomes = MockProvider().apply_msp_plan(_custom_plan(change))

    assert [outcome.action for outcome in outcomes] == ["conflict"]
    assert outcomes[0].details["reason"] == "duplicate live managed_company name: Acme"


def test_non_msp_resource_type_rejected_with_offending_uid_ref() -> None:
    change = Change(
        kind=ChangeKind.CREATE,
        uid_ref="machine.one",
        resource_type="pamMachine",
        title="machine-one",
        after={"title": "machine-one"},
    )

    with pytest.raises(ValueError, match="machine.one"):
        MockProvider().apply_msp_plan(_custom_plan(change))


def test_missing_update_target_skips_without_creating() -> None:
    change = Change(
        kind=ChangeKind.UPDATE,
        uid_ref="Ghost",
        resource_type="managed_company",
        title="Ghost",
        keeper_uid="123",
        after=_mc("Ghost", seats=8),
    )
    provider = MockProvider()

    outcomes = provider.apply_msp_plan(_custom_plan(change))

    assert outcomes[0].details["skipped"] == "record_missing"
    assert provider.discover_managed_companies() == []


def test_missing_delete_target_skips_without_creating() -> None:
    change = Change(
        kind=ChangeKind.DELETE,
        uid_ref="Ghost",
        resource_type="managed_company",
        title="Ghost",
        keeper_uid="123",
        before=_mc("Ghost"),
    )
    provider = MockProvider()

    outcomes = provider.apply_msp_plan(_custom_plan(change))

    assert outcomes[0].details["skipped"] == "record_missing"
    assert provider.discover_managed_companies() == []


def test_case_insensitive_identity_updates_existing_row() -> None:
    provider = MockProvider()
    provider.seed_managed_companies([_mc("acme", seats=5)])
    manifest = _manifest(_mc("Acme", seats=7))

    outcomes = provider.apply_msp_plan(_plan(manifest, provider))

    assert [outcome.action for outcome in outcomes] == ["update"]
    assert provider.discover_managed_companies()[0]["name"] == "Acme"
    assert (
        compute_msp_diff(manifest, provider.discover_managed_companies())[0].kind is ChangeKind.NOOP
    )


def test_rename_creates_new_id_slice1_known_limitation() -> None:
    provider = MockProvider()
    provider.seed_managed_companies([_mc("Old")])
    old_id = provider.discover_managed_companies()[0]["mc_enterprise_id"]
    manifest = _manifest(_mc("New"))

    outcomes = provider.apply_msp_plan(_plan(manifest, provider, allow_delete=True))

    assert [outcome.action for outcome in outcomes] == ["create", "delete"]
    assert outcomes[0].details["mc_enterprise_id"] != old_id
    assert outcomes[1].keeper_uid == str(old_id)
    assert provider.discover_managed_companies()[0]["name"] == "New"


def test_dry_run_does_not_persist_mc_id() -> None:
    provider = MockProvider()

    provider.apply_msp_plan(_plan(_manifest(_mc("Acme")), provider), dry_run=True)

    assert provider.discover_managed_companies() == []


def test_no_marker_field_written_for_managed_company() -> None:
    provider = MockProvider()

    provider.apply_msp_plan(_plan(_manifest(_mc("Acme")), provider))

    assert "custom_fields" not in provider.discover_managed_companies()[0]


def _commander_provider_for_msp(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[CommanderCliProvider, object]:
    provider = CommanderCliProvider.__new__(CommanderCliProvider)
    params = object()
    monkeypatch.setattr(provider, "_get_keeper_params", lambda: params)
    monkeypatch.setattr(provider, "_with_keeper_session_refresh", lambda operation: operation())
    return provider, params


def test_commander_msp_create_mc_calls_msp_add_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, params = _commander_provider_for_msp(monkeypatch)
    monkeypatch.setattr(provider, "discover_managed_companies", lambda: [])
    calls: list[tuple[object, dict[str, Any]]] = []

    class FakeMSPAddCommand:
        def execute(self, params_arg: object, **kwargs: Any) -> int:
            calls.append((params_arg, kwargs))
            return 456

    module = types.ModuleType("keepercommander.commands.msp")
    module.MSPAddCommand = FakeMSPAddCommand
    monkeypatch.setitem(sys.modules, "keepercommander.commands.msp", module)
    change = Change(
        kind=ChangeKind.CREATE,
        uid_ref="Acme",
        resource_type="managed_company",
        title="Acme",
        after=_mc(
            "Acme",
            seats=7,
            file_plan="enterprise",
            addons=[
                {"name": "connection_manager", "seats": 3},
                {"name": "remote_browser_isolation", "seats": 0},
            ],
        ),
    )

    outcomes = provider.apply_msp_plan(_custom_plan(change))

    assert [outcome.action for outcome in outcomes] == ["create"]
    assert outcomes[0].keeper_uid == "456"
    assert outcomes[0].details["mc_enterprise_id"] == 456
    assert calls == [
        (
            params,
            {
                "name": "Acme",
                "plan": "business",
                "seats": 7,
                "file_plan": "enterprise",
                "addon": ["connection_manager:3", "remote_browser_isolation"],
            },
        )
    ]


def test_commander_msp_create_mc_duplicate_name_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, _params = _commander_provider_for_msp(monkeypatch)
    monkeypatch.setattr(
        provider,
        "discover_managed_companies",
        lambda: [{"name": "acme", "mc_enterprise_id": 123}],
    )
    change = Change(
        kind=ChangeKind.CREATE,
        uid_ref="Acme",
        resource_type="managedCompany",
        title="Acme",
        after=_mc("Acme"),
    )

    with pytest.raises(ConflictError, match="already exists"):
        provider.apply_msp_plan(_custom_plan(change))


def test_commander_msp_update_mc_calls_msp_update_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, params = _commander_provider_for_msp(monkeypatch)
    monkeypatch.setattr(
        provider,
        "discover_managed_companies",
        lambda: [{"name": "Acme", "mc_enterprise_id": 123}],
    )
    calls: list[tuple[object, dict[str, Any]]] = []

    class FakeMSPUpdateCommand:
        def execute(self, params_arg: object, **kwargs: Any) -> None:
            calls.append((params_arg, kwargs))

    module = types.ModuleType("keepercommander.commands.msp")
    module.MSPUpdateCommand = FakeMSPUpdateCommand
    monkeypatch.setitem(sys.modules, "keepercommander.commands.msp", module)
    change = Change(
        kind=ChangeKind.UPDATE,
        uid_ref="Acme",
        resource_type="managed_company",
        title="Acme",
        keeper_uid="123",
        before=_mc(
            "Acme",
            seats=5,
            addons=[
                {"name": "connection_manager", "seats": 2},
                {"name": "old_addon", "seats": 0},
            ],
        ),
        after=_mc(
            "Acme",
            seats=9,
            file_plan="enterprise",
            addons=[
                {"name": "connection_manager", "seats": 3},
                {"name": "remote_browser_isolation", "seats": 0},
            ],
        ),
    )

    outcomes = provider.apply_msp_plan(_custom_plan(change))

    assert [outcome.action for outcome in outcomes] == ["update"]
    assert outcomes[0].keeper_uid == "123"
    assert calls == [
        (
            params,
            {
                "mc": "123",
                "name": "Acme",
                "plan": "business",
                "seats": 9,
                "file_plan": "enterprise",
                "add_addon": ["connection_manager:3", "remote_browser_isolation"],
                "remove_addon": ["old_addon"],
            },
        )
    ]


def test_commander_msp_delete_mc_calls_msp_remove_command_with_force(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, params = _commander_provider_for_msp(monkeypatch)
    monkeypatch.setattr(
        provider,
        "discover_managed_companies",
        lambda: [{"name": "Old", "mc_enterprise_id": 123}],
    )
    calls: list[tuple[object, dict[str, Any]]] = []

    class FakeMSPRemoveCommand:
        def execute(self, params_arg: object, **kwargs: Any) -> None:
            calls.append((params_arg, kwargs))

    module = types.ModuleType("keepercommander.commands.msp")
    module.MSPRemoveCommand = FakeMSPRemoveCommand
    monkeypatch.setitem(sys.modules, "keepercommander.commands.msp", module)
    change = Change(
        kind=ChangeKind.DELETE,
        uid_ref="Old",
        resource_type="managed_company",
        title="Old",
        keeper_uid="123",
        before=_mc("Old"),
    )

    outcomes = provider.apply_msp_plan(_custom_plan(change, allow_delete=True))

    assert [outcome.action for outcome in outcomes] == ["delete"]
    assert outcomes[0].keeper_uid == "123"
    assert calls == [(params, {"mc": "123", "force": True})]


def test_commander_msp_delete_mc_requires_allow_delete_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, _params = _commander_provider_for_msp(monkeypatch)
    monkeypatch.setattr(
        provider,
        "discover_managed_companies",
        lambda: [{"name": "Old", "mc_enterprise_id": 123}],
    )
    change = Change(
        kind=ChangeKind.DELETE,
        uid_ref="Old",
        resource_type="managed_company",
        title="Old",
        keeper_uid="123",
        before=_mc("Old"),
    )

    with pytest.raises(CapabilityError, match="allow_delete=True"):
        provider.apply_msp_plan(_custom_plan(change, allow_delete=False))
