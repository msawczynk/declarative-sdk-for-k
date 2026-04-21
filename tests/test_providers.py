"""MockProvider round-trip: apply creates records, second plan is clean."""

from __future__ import annotations

from pathlib import Path

from keeper_sdk.core import (
    build_graph,
    build_plan,
    compute_diff,
    execution_order,
    load_manifest,
)
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.providers import MockProvider


def test_apply_then_replan_is_mostly_noop(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    provider = MockProvider(manifest.name)

    graph = build_graph(manifest)
    order = execution_order(graph)

    # first apply -> all creates
    changes = compute_diff(manifest, provider.discover())
    plan = build_plan(manifest.name, changes, order)
    outcomes = provider.apply_plan(plan)
    assert all(o.action in ("create", "noop") for o in outcomes)
    assert len([o for o in outcomes if o.action == "create"]) >= 1

    # replan -> no creates (records now carry our markers)
    changes2 = compute_diff(manifest, provider.discover())
    creates = [c for c in changes2 if c.kind is ChangeKind.CREATE]
    assert creates == []


def test_delete_with_allow_delete(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    provider = MockProvider(manifest.name)
    graph = build_graph(manifest)
    order = execution_order(graph)

    plan = build_plan(
        manifest.name,
        compute_diff(manifest, provider.discover()),
        order,
    )
    provider.apply_plan(plan)

    # seed an orphan owned by the same manifest
    provider.seed_payload(
        title="retired-host",
        resource_type="pamMachine",
        payload={"title": "retired-host"},
        marker_uid_ref="retired",
        manifest_name=manifest.name,
    )

    changes = compute_diff(manifest, provider.discover(), allow_delete=True)
    deletes = [c for c in changes if c.kind is ChangeKind.DELETE]
    assert any(c.title == "retired-host" for c in deletes)

    plan2 = build_plan(manifest.name, changes, order)
    outcomes = provider.apply_plan(plan2)
    assert any(o.action == "delete" for o in outcomes)
