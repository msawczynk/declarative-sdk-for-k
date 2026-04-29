"""Dependency graph for ``keeper-ksm.v1`` manifests.

Convention matches :mod:`keeper_sdk.core.graph`: a directed edge ``A -> B`` means
``A`` depends on ``B``. Tokens, shares, and config outputs therefore depend on
their app; record shares also depend on a synthetic vault-record reference node.
"""

from __future__ import annotations

import re

import networkx as nx

from keeper_sdk.core.errors import RefError
from keeper_sdk.core.graph import execution_order
from keeper_sdk.core.models_ksm import (
    KsmManifestV1,
    config_output_key,
    share_key,
)

KSM_SHARE_NODE_PREFIX = "_ksm_share:"
KSM_CONFIG_OUTPUT_NODE_PREFIX = "_ksm_config_output:"
KSM_RECORD_NODE_PREFIX = "_ksm_record:"

_APP_REF_RE = re.compile(r"^keeper-ksm:apps:(?P<uid_ref>[A-Za-z0-9][A-Za-z0-9_.:-]{0,127})$")
_RECORD_REF_RE = re.compile(
    r"^keeper-vault:records:(?P<uid_ref>[A-Za-z0-9][A-Za-z0-9_.:-]{0,127})$"
)


def build_ksm_graph(manifest: KsmManifestV1) -> nx.DiGraph:
    """Return a directed graph over KSM object nodes.

    Raises :class:`RefError` for duplicate ``uid_ref`` values, malformed refs,
    unresolved local app refs, or dependency cycles.
    """
    graph: nx.DiGraph = nx.DiGraph()
    owners: dict[str, str] = {}
    dup: list[str] = []

    for uid_ref, kind in manifest.iter_uid_refs():
        if uid_ref in owners:
            dup.append(uid_ref)
        owners[uid_ref] = kind
        graph.add_node(uid_ref, kind=kind)

    if dup:
        raise RefError(
            reason=f"duplicate uid_ref values: {sorted(set(dup))}",
            next_action="rename duplicates so every uid_ref is unique",
        )

    for token in manifest.tokens:
        app_uid_ref = _local_app_uid_ref(token.app_uid_ref, owner=token.uid_ref)
        _assert_app_exists(owners, app_uid_ref, owner=token.uid_ref)
        graph.add_edge(token.uid_ref, app_uid_ref)

    for share in manifest.record_shares:
        node_id = f"{KSM_SHARE_NODE_PREFIX}{share_key(share)}"
        graph.add_node(node_id, kind="ksm_record_share")
        app_uid_ref = _local_app_uid_ref(share.app_uid_ref, owner=node_id)
        _assert_app_exists(owners, app_uid_ref, owner=node_id)
        graph.add_edge(node_id, app_uid_ref)

        record_node = _record_graph_id(share.record_uid_ref, owner=node_id)
        graph.add_node(record_node, kind="vault_record_ref")
        graph.add_edge(node_id, record_node)

    for output in manifest.config_outputs:
        node_id = f"{KSM_CONFIG_OUTPUT_NODE_PREFIX}{config_output_key(output)}"
        graph.add_node(node_id, kind="ksm_config_output")
        app_uid_ref = _local_app_uid_ref(output.app_uid_ref, owner=node_id)
        _assert_app_exists(owners, app_uid_ref, owner=node_id)
        graph.add_edge(node_id, app_uid_ref)

    _assert_acyclic(graph)
    return graph


def ksm_apply_order(manifest: KsmManifestV1) -> list[str]:
    """Return dependency-safe KSM action nodes; synthetic vault records are dropped."""
    order = execution_order(build_ksm_graph(manifest))
    return [node for node in order if not node.startswith(KSM_RECORD_NODE_PREFIX)]


def _local_app_uid_ref(ref: str, *, owner: str) -> str:
    match = _APP_REF_RE.match(ref)
    if not match:
        raise RefError(
            reason=f"malformed keeper-ksm app reference {ref!r}",
            uid_ref=owner,
            next_action="use keeper-ksm:apps:<uid_ref> for KSM app references",
        )
    return match.group("uid_ref")


def _record_graph_id(ref: str, *, owner: str) -> str:
    if not _RECORD_REF_RE.match(ref):
        raise RefError(
            reason=f"malformed keeper-vault record reference {ref!r}",
            uid_ref=owner,
            next_action="use keeper-vault:records:<uid_ref> for vault record references",
        )
    return f"{KSM_RECORD_NODE_PREFIX}{ref}"


def _assert_app_exists(owners: dict[str, str], uid_ref: str, *, owner: str) -> None:
    if uid_ref not in owners or owners[uid_ref] != "ksm_app":
        raise RefError(
            reason=f"reference to unknown KSM app uid_ref '{uid_ref}' from '{owner}'",
            uid_ref=owner,
            next_action="add the target app or fix app_uid_ref",
        )


def _assert_acyclic(graph: nx.DiGraph) -> None:
    try:
        cycle = nx.find_cycle(graph)
    except nx.NetworkXNoCycle:
        return
    raise RefError(
        reason=f"dependency cycle detected: {cycle}",
        next_action="break the cycle by removing a reference",
    )


__all__ = ["build_ksm_graph", "ksm_apply_order"]
