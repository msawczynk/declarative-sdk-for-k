"""Dependency graph for ``msp-environment.v1`` manifests (Sprint 7h-59 / P2).

Slice-1 managed companies have **no inter-MC dependencies** (cross-family
refs are out of scope per docs/MSP_FAMILY_DESIGN.md §10 Q10). The graph is
therefore a flat node set with one node per managed company; topological
order falls back to a deterministic alphabetical sort by ``name`` so
``apply`` produces the same row order across runs.

Convention matches :mod:`keeper_sdk.core.graph` (also used by
:mod:`keeper_sdk.core.vault_graph`): a directed edge ``A -> B`` means
**A depends on B**. No edges are emitted in slice 1; see
:func:`msp_apply_order`.
"""

from __future__ import annotations

import networkx as nx

from keeper_sdk.core.errors import RefError
from keeper_sdk.core.msp_models import MspManifestV1

__all__ = ["build_msp_graph", "msp_apply_order"]


def build_msp_graph(manifest: MspManifestV1) -> nx.DiGraph:
    """Return a directed graph over managed-company name nodes.

    Each node id is the MC ``name``; node attribute ``kind="managed_company"``.
    Slice 1 emits no edges (MCs are independent).

    Raises :class:`RefError` on duplicate ``name`` values. (``apply_semantic_rules``
    in :mod:`keeper_sdk.core.rules` enforces the same invariant earlier in the
    pipeline; this layer is defense-in-depth for callers that skip rules.)
    """
    graph: nx.DiGraph = nx.DiGraph()
    seen: set[str] = set()
    dup: list[str] = []
    for mc in manifest.managed_companies:
        if mc.name in seen:
            dup.append(mc.name)
        else:
            seen.add(mc.name)
        graph.add_node(mc.name, kind="managed_company")

    if dup:
        raise RefError(
            reason=f"duplicate managed_company name values: {sorted(set(dup))}",
            next_action="rename duplicates so every managed_company name is unique",
        )

    return graph


def msp_apply_order(manifest: MspManifestV1) -> list[str]:
    """Return managed-company names in deterministic apply order.

    Alphabetical by ``name`` (case-sensitive, Unicode default). Slice 1
    has no dependency edges; future slices that introduce cross-MC or
    cross-family references should switch to :func:`execution_order`
    over :func:`build_msp_graph`'s output.
    """
    graph = build_msp_graph(manifest)
    return sorted(graph.nodes())
