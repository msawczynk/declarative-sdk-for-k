"""Tests for keeper_sdk.core.msp_diff (P3)."""

from __future__ import annotations

from typing import Any

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.msp_diff import compute_msp_diff
from keeper_sdk.core.msp_models import MspManifestV1, load_msp_manifest


def _manifest(
    *managed_companies: dict[str, Any],
    manager: str | None = None,
) -> MspManifestV1:
    document: dict[str, Any] = {
        "schema": "msp-environment.v1",
        "name": "msp-diff-test",
        "managed_companies": list(managed_companies),
    }
    if manager is not None:
        document["manager"] = manager
    return load_msp_manifest(document)


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


def _only(changes: list[Change]) -> Change:
    assert len(changes) == 1
    return changes[0]


def test_empty_manifest_and_empty_live_has_no_changes() -> None:
    assert compute_msp_diff(_manifest(), []) == []


def test_create_when_manifest_mc_missing_from_live() -> None:
    row = _only(compute_msp_diff(_manifest(_mc("Acme")), []))

    assert row.kind is ChangeKind.CREATE
    assert row.resource_type == "managed_company"
    assert row.title == "Acme"
    assert row.before == {}
    assert row.after == {
        "name": "Acme",
        "plan": "business",
        "seats": 5,
        "file_plan": None,
        "addons": [],
    }


def test_delete_when_live_mc_missing_from_manifest_and_allow_delete_true() -> None:
    row = _only(compute_msp_diff(_manifest(), [_mc("Old")], allow_delete=True))

    assert row.kind is ChangeKind.DELETE
    assert row.title == "Old"
    assert row.reason is None
    assert row.before["name"] == "Old"


def test_skip_when_live_mc_missing_from_manifest_and_allow_delete_false() -> None:
    row = _only(compute_msp_diff(_manifest(), [_mc("Old")]))

    assert row.kind is ChangeKind.SKIP
    assert row.title == "Old"
    assert row.reason == "unmanaged managed_company; pass allow_delete=True to remove"


def test_update_when_seats_drift() -> None:
    row = _only(compute_msp_diff(_manifest(_mc("Acme", seats=7)), [_mc("Acme", seats=5)]))

    assert row.kind is ChangeKind.UPDATE
    assert row.before["seats"] == 5
    assert row.after["seats"] == 7


def test_update_when_plan_drift() -> None:
    row = _only(
        compute_msp_diff(
            _manifest(_mc("Acme", plan="enterprise")),
            [_mc("Acme", plan="business")],
        )
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.before["plan"] == "business"
    assert row.after["plan"] == "enterprise"


def test_file_plan_none_and_empty_string_are_noop() -> None:
    row = _only(
        compute_msp_diff(
            _manifest(_mc("Acme", file_plan=None)),
            [_mc("Acme", file_plan="")],
        )
    )

    assert row.kind is ChangeKind.NOOP
    assert row.reason == "no drift"
    assert row.before["file_plan"] is None
    assert row.after["file_plan"] is None


def test_addons_order_ignored_but_seat_drift_updates() -> None:
    desired = _manifest(
        _mc(
            "Acme",
            addons=[
                {"name": "remote_browser_isolation", "seats": 2},
                {"name": "connection_manager", "seats": 1},
            ],
        )
    )
    same_live = [
        _mc(
            "Acme",
            addons=[
                {"name": "connection_manager", "seats": 1},
                {"name": "remote_browser_isolation", "seats": 2},
            ],
        )
    ]
    changed_live = [
        _mc(
            "Acme",
            addons=[
                {"name": "connection_manager", "seats": 1},
                {"name": "remote_browser_isolation", "seats": 1},
            ],
        )
    ]

    same = _only(compute_msp_diff(desired, same_live))
    changed = _only(compute_msp_diff(desired, changed_live))

    assert same.kind is ChangeKind.NOOP
    assert same.after["addons"] == [
        {"name": "connection_manager", "seats": 1},
        {"name": "remote_browser_isolation", "seats": 2},
    ]
    assert changed.kind is ChangeKind.UPDATE
    assert changed.before["addons"][1]["seats"] == 1
    assert changed.after["addons"][1]["seats"] == 2


def test_case_insensitive_name_match_preserves_manifest_casing() -> None:
    row = _only(compute_msp_diff(_manifest(_mc("Acme")), [_mc("acme")]))

    assert row.kind is ChangeKind.NOOP
    assert row.title == "Acme"
    assert row.before["name"] == "acme"
    assert row.after["name"] == "Acme"


def test_adopt_unmanaged_name_match_emits_update_marker_change() -> None:
    row = _only(
        compute_msp_diff(
            _manifest(_mc("Acme"), manager="keeper-msp-declarative"),
            [_mc("acme")],
            adopt=True,
        )
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.title == "Acme"
    assert row.before["name"] == "acme"
    assert row.after["manager"] == "keeper-msp-declarative"
    assert "adoption" in (row.reason or "")


def test_adopt_skips_live_row_already_marked_by_manifest_manager() -> None:
    live = _mc("Acme", seats=1)
    live["manager"] = "keeper-msp-declarative"

    row = _only(
        compute_msp_diff(
            _manifest(_mc("Acme", seats=9), manager="keeper-msp-declarative"),
            [live],
            adopt=True,
        )
    )

    assert row.kind is ChangeKind.NOOP
    assert "adoption" not in (row.reason or "")


def test_foreign_live_manager_conflicts() -> None:
    live = _mc("Acme")
    live["manager"] = "other-manager"

    row = _only(
        compute_msp_diff(
            _manifest(_mc("Acme"), manager="keeper-msp-declarative"),
            [live],
            adopt=True,
        )
    )

    assert row.kind is ChangeKind.CONFLICT
    assert "managed by other" in (row.reason or "")


def test_conflict_on_duplicate_live_names() -> None:
    row = _only(compute_msp_diff(_manifest(_mc("Acme")), [_mc("Acme"), _mc("acme")]))

    assert row.kind is ChangeKind.CONFLICT
    assert row.reason == "duplicate live managed_company name: Acme"
    assert row.before == {"names": ["Acme", "acme"]}


def test_seat_unlimited_sentinels_canonicalise() -> None:
    manifest = _manifest(_mc("Minus", seats=1_000_000_000), _mc("Huge", seats=1_000_000_000))
    rows = compute_msp_diff(
        manifest,
        [
            _mc("Minus", seats=-1),
            _mc("Huge", seats=999_999_999_999),
        ],
    )

    assert [row.kind for row in rows] == [ChangeKind.NOOP, ChangeKind.NOOP]
    assert {row.title: row.before["seats"] for row in rows} == {
        "Huge": 1_000_000_000,
        "Minus": 1_000_000_000,
    }


def test_mixed_scenario_orders_create_update_noop_skip() -> None:
    changes = compute_msp_diff(
        _manifest(
            _mc("Bravo"),
            _mc("Alpha"),
            _mc("Update", seats=10),
            _mc("Stable"),
        ),
        [
            _mc("Update", seats=5),
            _mc("Stable"),
            _mc("Old"),
        ],
    )

    assert [(row.kind, row.title) for row in changes] == [
        (ChangeKind.CREATE, "Alpha"),
        (ChangeKind.CREATE, "Bravo"),
        (ChangeKind.UPDATE, "Update"),
        (ChangeKind.NOOP, "Stable"),
        (ChangeKind.SKIP, "Old"),
    ]
