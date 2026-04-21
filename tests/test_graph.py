"""Graph + topological order."""

from __future__ import annotations

from pathlib import Path

import pytest

from keeper_sdk.core import build_graph, execution_order, load_manifest
from keeper_sdk.core.errors import RefError


def test_build_graph_minimal(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    graph = build_graph(manifest)
    assert "acme-lab-linux1" in graph
    assert graph.has_edge("acme-lab-linux1", "acme-lab-cfg")


def test_topological_order_has_leaves_first(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    graph = build_graph(manifest)
    order = execution_order(graph)
    gateway_idx = order.index("acme-lab-gw")
    config_idx = order.index("acme-lab-cfg")
    resource_idx = order.index("acme-lab-linux1")
    assert gateway_idx < config_idx < resource_idx


def test_cycle_detected() -> None:
    """execution_order must reject cycles."""
    import networkx as nx

    graph: nx.DiGraph = nx.DiGraph()
    graph.add_edge("a", "b")
    graph.add_edge("b", "a")
    with pytest.raises(RefError):
        execution_order(graph)
