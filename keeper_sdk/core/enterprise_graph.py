"""Dependency graph for ``keeper-enterprise.v1`` manifests.

Convention matches :mod:`keeper_sdk.core.graph`: a directed edge ``A -> B`` means
``A`` depends on ``B``. Node children therefore depend on parents; teams can
depend on roles and users; roles can depend on users.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

import networkx as nx

from keeper_sdk.core.errors import RefError
from keeper_sdk.core.graph import execution_order
from keeper_sdk.core.models_enterprise import EnterpriseManifestV1

_REF_RE = re.compile(
    r"^keeper-enterprise:(?P<block>nodes|users|roles|teams):(?P<uid_ref>[A-Za-z0-9][A-Za-z0-9_.:-]{0,127})$"
)

_EXPECTED_BLOCK_BY_KIND = {
    "enterprise_node": "nodes",
    "enterprise_user": "users",
    "enterprise_role": "roles",
    "enterprise_team": "teams",
    "enterprise_enforcement": "enforcements",
    "enterprise_alias": "aliases",
}


def build_enterprise_graph(manifest: EnterpriseManifestV1) -> nx.DiGraph:
    """Return a directed graph over enterprise ``uid_ref`` nodes.

    Raises :class:`RefError` for duplicate ``uid_ref`` values, malformed refs,
    unresolved local refs, or dependency cycles.
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

    for node in manifest.nodes:
        _add_ref_edge(
            graph,
            owners,
            owner=node.uid_ref,
            ref=node.parent_uid_ref,
            expected_block="nodes",
        )

    for user in manifest.users:
        _add_ref_edge(
            graph,
            owners,
            owner=user.uid_ref,
            ref=user.node_uid_ref,
            expected_block="nodes",
        )

    for role in manifest.roles:
        _add_ref_edge(
            graph,
            owners,
            owner=role.uid_ref,
            ref=role.node_uid_ref,
            expected_block="nodes",
        )
        _add_many_ref_edges(
            graph,
            owners,
            owner=role.uid_ref,
            refs=role.user_uid_refs,
            expected_block="users",
        )

    for team in manifest.teams:
        _add_ref_edge(
            graph,
            owners,
            owner=team.uid_ref,
            ref=team.node_uid_ref,
            expected_block="nodes",
        )
        _add_many_ref_edges(
            graph,
            owners,
            owner=team.uid_ref,
            refs=team.role_uid_refs,
            expected_block="roles",
        )
        _add_many_ref_edges(
            graph,
            owners,
            owner=team.uid_ref,
            refs=team.user_uid_refs,
            expected_block="users",
        )

    for enforcement in manifest.enforcements:
        _add_ref_edge(
            graph,
            owners,
            owner=enforcement.uid_ref,
            ref=enforcement.role_uid_ref,
            expected_block="roles",
        )

    for alias in manifest.aliases:
        _add_ref_edge(
            graph,
            owners,
            owner=alias.uid_ref,
            ref=alias.user_uid_ref,
            expected_block="users",
        )

    _assert_acyclic(graph)
    return graph


def enterprise_apply_order(manifest: EnterpriseManifestV1) -> list[str]:
    """Return enterprise ``uid_ref`` values in dependency-safe order."""
    return execution_order(build_enterprise_graph(manifest))


def _add_many_ref_edges(
    graph: nx.DiGraph,
    owners: dict[str, str],
    *,
    owner: str,
    refs: Iterable[str],
    expected_block: str,
) -> None:
    for ref in refs:
        _add_ref_edge(
            graph,
            owners,
            owner=owner,
            ref=ref,
            expected_block=expected_block,
        )


def _add_ref_edge(
    graph: nx.DiGraph,
    owners: dict[str, str],
    *,
    owner: str,
    ref: str | None,
    expected_block: str,
) -> None:
    if ref is None:
        return
    target = _local_uid_ref(ref, owner=owner, expected_block=expected_block)
    if target not in owners:
        raise RefError(
            reason=f"reference to unknown uid_ref '{target}' from '{owner}'",
            uid_ref=owner,
            next_action="add the target object or fix the uid_ref",
        )
    actual_block = _EXPECTED_BLOCK_BY_KIND.get(owners[target])
    if actual_block != expected_block:
        raise RefError(
            reason=(
                f"reference {ref!r} from {owner!r} points at {actual_block!r}, "
                f"expected {expected_block!r}"
            ),
            uid_ref=owner,
            next_action="fix the reference block or target uid_ref",
        )
    graph.add_edge(owner, target)


def _local_uid_ref(ref: str, *, owner: str, expected_block: str) -> str:
    match = _REF_RE.match(ref)
    if not match:
        raise RefError(
            reason=f"malformed keeper-enterprise reference {ref!r}",
            uid_ref=owner,
            next_action=(
                f"use keeper-enterprise:{expected_block}:<uid_ref> for keeper-enterprise references"
            ),
        )
    block = match.group("block")
    if block != expected_block:
        raise RefError(
            reason=f"reference {ref!r} uses block {block!r}, expected {expected_block!r}",
            uid_ref=owner,
            next_action="fix the reference block",
        )
    return match.group("uid_ref")


def _assert_acyclic(graph: nx.DiGraph) -> None:
    try:
        cycle = nx.find_cycle(graph)
    except nx.NetworkXNoCycle:
        return
    raise RefError(
        reason=f"dependency cycle detected: {cycle}",
        next_action="break the cycle by removing a reference",
    )


__all__ = ["build_enterprise_graph", "enterprise_apply_order"]
