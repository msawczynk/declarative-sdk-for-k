"""Dependency graph for ``keeper-vault-sharing.v1`` manifests."""

from __future__ import annotations

import re

import networkx as nx

from keeper_sdk.core.errors import RefError
from keeper_sdk.core.graph import execution_order
from keeper_sdk.core.sharing_models import SharingManifestV1

_SHARING_REF_RE = re.compile(
    r"^keeper-vault-sharing:(?P<block>folders|shared_folders):(?P<uid_ref>.+)$"
)


def build_sharing_graph(manifest: SharingManifestV1) -> nx.DiGraph:
    """Return a dependency graph over sharing ``uid_ref`` nodes.

    Raises :class:`RefError` for duplicate sharing ``uid_ref`` values,
    unresolved local shared-folder member refs, or dependency cycles.
    """

    graph: nx.DiGraph = nx.DiGraph()
    owners: dict[str, str] = {}
    duplicates: list[str] = []

    for uid_ref, kind in _iter_uid_refs(manifest):
        if uid_ref in owners:
            duplicates.append(uid_ref)
        owners[uid_ref] = kind
        graph.add_node(uid_ref, kind=kind)

    if duplicates:
        raise RefError(
            reason=f"duplicate uid_ref values: {sorted(set(duplicates))}",
            next_action="rename duplicates so every uid_ref is unique",
        )

    for folder in manifest.folders:
        if folder.parent_folder_uid_ref:
            target = _sharing_ref_uid_ref(folder.parent_folder_uid_ref, owner=folder.uid_ref)
            if target in owners:
                graph.add_edge(folder.uid_ref, target)

    for share in manifest.share_folders:
        target = _sharing_ref_uid_ref(share.shared_folder_uid_ref, owner=share.uid_ref)
        if owners.get(target) != "sharing_shared_folder":
            raise RefError(
                reason=(
                    f"reference to unknown shared_folder uid_ref '{target}' from '{share.uid_ref}'"
                ),
                uid_ref=share.uid_ref,
                resource_type="sharing_share_folder",
                next_action="add the target shared_folders[] row or fix shared_folder_uid_ref",
            )
        graph.add_edge(share.uid_ref, target)

    _assert_acyclic(graph)
    return graph


def sharing_apply_order(manifest: SharingManifestV1) -> list[str]:
    """Return dependency-safe sharing action order."""

    return execution_order(build_sharing_graph(manifest))


def _iter_uid_refs(manifest: SharingManifestV1) -> list[tuple[str, str]]:
    return [
        *((folder.uid_ref, "sharing_folder") for folder in manifest.folders),
        *((folder.uid_ref, "sharing_shared_folder") for folder in manifest.shared_folders),
        *((share.uid_ref, "sharing_record_share") for share in manifest.share_records),
        *((share.uid_ref, "sharing_share_folder") for share in manifest.share_folders),
    ]


def _sharing_ref_uid_ref(ref: str, *, owner: str) -> str:
    match = _SHARING_REF_RE.match(ref)
    if not match:
        raise RefError(
            reason=f"malformed keeper-vault-sharing reference {ref!r}",
            uid_ref=owner,
            next_action="use keeper-vault-sharing:(folders|shared_folders):<uid_ref>",
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


__all__ = ["build_sharing_graph", "sharing_apply_order"]
