"""Offline coverage for two-writer ownership marker conflicts."""

from __future__ import annotations

from typing import Any

import pytest

import keeper_sdk.core.diff as diff_module
import keeper_sdk.core.metadata as metadata_module
from keeper_sdk.core import build_graph, build_plan, compute_diff, execution_order
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.manifest import load_manifest_string
from keeper_sdk.core.models import Manifest
from keeper_sdk.providers import MockProvider

RESOURCE_UID_REF = "res.shared"
RESOURCE_TITLE = "two-writer-host"


def _set_agent_manager(monkeypatch: pytest.MonkeyPatch, manager: str) -> None:
    monkeypatch.setattr(metadata_module, "MANAGER_NAME", manager)
    monkeypatch.setattr(diff_module, "MANAGER_NAME", manager)


def _manifest(name: str, *, include_resource: bool = True) -> Manifest:
    resources = (
        f"""
resources:
  - uid_ref: {RESOURCE_UID_REF}
    type: pamMachine
    title: {RESOURCE_TITLE}
"""
        if include_resource
        else "resources: []\n"
    )
    return load_manifest_string(
        f"""
version: "1"
name: {name}
{resources}
""",
        suffix=".yaml",
    )


def _plan(
    manifest: Manifest,
    provider: MockProvider,
    *,
    allow_delete: bool = False,
    adopt: bool = False,
) -> Any:
    order = execution_order(build_graph(manifest))
    changes = compute_diff(
        manifest,
        provider.discover(),
        manifest_name=manifest.name,
        allow_delete=allow_delete,
        adopt=adopt,
    )
    return build_plan(manifest.name, changes, order)


def _apply_cleanly(manifest: Manifest, provider: MockProvider) -> None:
    plan = _plan(manifest, provider)

    assert [change.kind for change in plan.creates] == [ChangeKind.CREATE]
    assert not plan.conflicts
    assert [outcome.action for outcome in provider.apply_plan(plan)] == ["create"]


def test_second_writer_apply_and_import_return_conflict_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = MockProvider("two-writer-a")
    manifest_a = _manifest("two-writer-a")
    manifest_b = _manifest("two-writer-b")

    _set_agent_manager(monkeypatch, "agent-1")
    _apply_cleanly(manifest_a, provider)
    [owned] = provider.discover()
    assert owned.marker is not None
    assert owned.marker["manager"] == "agent-1"

    _set_agent_manager(monkeypatch, "agent-2")
    apply_plan = _plan(manifest_b, provider)
    import_plan = _plan(manifest_b, provider, adopt=True)

    for plan in (apply_plan, import_plan):
        assert [change.kind for change in plan.conflicts] == [ChangeKind.CONFLICT]
        conflict = plan.conflicts[0]
        assert conflict.uid_ref == RESOURCE_UID_REF
        assert conflict.keeper_uid == owned.keeper_uid
        assert conflict.reason == "record managed by 'agent-1', refusing to touch"


def test_same_manager_second_apply_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = MockProvider("two-writer")
    manifest = _manifest("two-writer")

    _set_agent_manager(monkeypatch, "agent-1")
    _apply_cleanly(manifest, provider)

    replan = _plan(manifest, provider)

    assert not replan.conflicts
    assert replan.is_clean
    assert [change.kind for change in replan.noops] == [ChangeKind.NOOP]
    assert replan.noops[0].uid_ref == RESOURCE_UID_REF


def test_second_writer_can_adopt_after_explicit_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = MockProvider("two-writer-a")
    manifest_a = _manifest("two-writer-a")

    _set_agent_manager(monkeypatch, "agent-1")
    _apply_cleanly(manifest_a, provider)

    release_manifest = _manifest("two-writer-a", include_resource=False)
    release_plan = _plan(release_manifest, provider, allow_delete=True)

    assert [change.kind for change in release_plan.deletes] == [ChangeKind.DELETE]
    assert [outcome.action for outcome in provider.apply_plan(release_plan)] == ["delete"]
    assert provider.discover() == []

    provider.seed(
        [
            LiveRecord(
                keeper_uid="LIVE-RELEASED",
                title=RESOURCE_TITLE,
                resource_type="pamMachine",
                payload={"title": RESOURCE_TITLE},
                marker=None,
            )
        ]
    )

    _set_agent_manager(monkeypatch, "agent-2")
    adopt_manifest = _manifest("two-writer-b")
    adopt_plan = _plan(adopt_manifest, provider, adopt=True)

    assert not adopt_plan.conflicts
    assert [change.kind for change in adopt_plan.updates] == [ChangeKind.UPDATE]
    assert adopt_plan.updates[0].reason == "adoption: write ownership marker"

    assert [outcome.action for outcome in provider.apply_plan(adopt_plan)] == ["update"]
    [adopted] = provider.discover()
    assert adopted.marker is not None
    assert adopted.marker["manager"] == "agent-2"
    assert adopted.marker["manifest"] == "two-writer-b"
