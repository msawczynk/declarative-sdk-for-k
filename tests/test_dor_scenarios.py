"""Focused offline coverage for deferred DOR TEST_PLAN scenarios."""

from __future__ import annotations

from typing import Any

import pytest

from keeper_sdk.core import compute_diff
from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.manifest import load_manifest_string
from keeper_sdk.core.metadata import MANAGER_NAME, encode_marker
from keeper_sdk.core.planner import Plan
from keeper_sdk.providers.commander_cli import CommanderCliProvider


def _manifest(uid_ref: str, title: str) -> Any:
    return load_manifest_string(
        f"""
version: "1"
name: dor-scenarios
resources:
  - uid_ref: {uid_ref}
    type: pamMachine
    title: {title}
""",
        suffix=".yaml",
    )


def _commander_provider(
    monkeypatch: pytest.MonkeyPatch, manifest_name: str
) -> CommanderCliProvider:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    return CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source={"version": "1", "name": manifest_name, "resources": []},
    )


def test_adoption_race_unmanaged_record_emits_conflict() -> None:
    manifest_a = _manifest("writer-a", "X")
    manifest_b = _manifest("writer-b", "X")
    live = [
        LiveRecord(
            keeper_uid="LIVE-X",
            title="X",
            resource_type="pamMachine",
            payload={"title": "X"},
            marker=None,
        )
    ]

    changes_a = compute_diff(manifest_a, live, adopt=False)
    changes_b = compute_diff(manifest_b, live, adopt=False)

    for uid_ref, changes in (("writer-a", changes_a), ("writer-b", changes_b)):
        target = next(change for change in changes if change.uid_ref == uid_ref)
        assert target.kind is ChangeKind.CONFLICT
        assert target.keeper_uid == "LIVE-X"
        assert "unmanaged record with matching title" in (target.reason or "")


def test_partial_apply_rollback_records_outcome_then_raises() -> None:
    pytest.xfail(
        "deferred to v1.1 — see DOR TEST_PLAN.md partial-apply rollback scenario; "
        "create/update paths do not yet append a failed outcome before re-raising"
    )


def test_ksm_rotation_mid_apply_does_not_invalidate_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _commander_provider(monkeypatch, "dor-rotation")
    plan = Plan(
        manifest_name="dor-rotation",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="res.x",
                resource_type="pamMachine",
                title="X",
                after={"title": "X"},
            )
        ],
        order=["res.x"],
    )

    calls: list[list[str]] = []

    def fake_run_cmd(_self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        if len(calls) == 1:
            raise CapabilityError(
                reason="keeper pam project import failed (rc=1)",
                context={"stderr": "session expired"},
                next_action="re-login with a fresh Keeper session and re-run apply",
            )
        return ""

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", fake_run_cmd)

    with pytest.raises(CapabilityError) as exc_info:
        provider.apply_plan(plan)

    assert len(calls) == 1
    assert "re-login" in exc_info.value.next_action
    assert exc_info.value.context == {"stderr": "session expired"}


def test_commander_version_mismatch_surfaces_capability_error() -> None:
    pytest.xfail(
        "deferred to v1.1 — see DOR TEST_PLAN.md Commander version mismatch scenario; "
        "the provider has a documented pin but no production version gate yet"
    )


def test_stale_marker_cleanup_strips_unmanaged_when_record_gone() -> None:
    manifest = _manifest("res.x", "X")

    # Current architecture has no separate marker store during planning:
    # once discover() no longer returns the record, replanning sees no
    # orphan to delete and simply recreates the desired resource.
    changes = compute_diff(manifest, [], adopt=False, allow_delete=True)

    creates = [change for change in changes if change.kind is ChangeKind.CREATE]
    deletes = [change for change in changes if change.kind is ChangeKind.DELETE]
    assert [change.uid_ref for change in creates] == ["res.x"]
    assert deletes == []


def test_two_writer_conflict_second_writer_observes_marker_collision() -> None:
    manifest = _manifest("writer-b", "X")
    live = [
        LiveRecord(
            keeper_uid="LIVE-X",
            title="X",
            resource_type="pamMachine",
            payload={"title": "X"},
            marker={
                **encode_marker(
                    uid_ref="writer-a",
                    manifest="other-manifest",
                    resource_type="pamMachine",
                ),
                "manager": "competitor-tool",
            },
        )
    ]

    changes = compute_diff(manifest, live, adopt=False)

    target = next(change for change in changes if change.uid_ref == "writer-b")
    assert MANAGER_NAME != "competitor-tool"
    assert target.kind is ChangeKind.CONFLICT
    assert target.keeper_uid == "LIVE-X"
    assert target.reason == "record managed by 'competitor-tool', refusing to touch"
