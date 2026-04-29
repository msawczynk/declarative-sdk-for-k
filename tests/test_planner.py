from pathlib import Path

from keeper_sdk.core import (
    build_graph,
    build_plan,
    compute_diff,
    execution_order,
    load_manifest,
)
from keeper_sdk.core.diff import ChangeKind


def test_ordered_plan_creates_deps_first(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    graph = build_graph(manifest)
    order = execution_order(graph)
    changes = compute_diff(manifest, live_records=[])
    plan = build_plan(manifest.name, changes, order)
    uids = [c.uid_ref for c in plan.ordered() if c.kind is ChangeKind.CREATE and c.uid_ref]
    assert uids.index("acme-lab-cfg") < uids.index("acme-lab-linux1")


def test_plan_is_clean_when_no_changes(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    plan = build_plan(manifest.name, [], [])
    assert plan.is_clean
