"""Dependency graph on ``uid_ref``.

Convention (read before changing edges): a directed edge ``A -> B`` means
**A depends on B** — B is a prerequisite of A. :func:`execution_order` lists
nodes so dependencies appear before dependents. This is easy to invert when
English talks about a resource "owning" nested ``pamUser`` rows; containment
is modeled with **child -> parent** edges so nested users sort *after* their
host.

Edges are built from the fixed reference-bearing fields defined in the schema
(``*_uid_ref`` keys). We intentionally do not guess by-title references — the
manifest is expected to be canonicalised before this stage.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import networkx as nx

from keeper_sdk.core.errors import RefError
from keeper_sdk.core.models import Manifest

# fields whose value is a single uid_ref pointer
_SCALAR_REF_FIELDS = (
    "pam_configuration_uid_ref",
    "gateway_uid_ref",
    "administrative_credentials_uid_ref",
    "launch_credentials_uid_ref",
    "autofill_credentials_uid_ref",
    "sftp_user_credentials_uid_ref",
    "sftp_resource_uid_ref",
    "pam_directory_uid_ref",
    "dom_administrative_credential_uid_ref",
)

# fields whose value is a list of uid_refs
_LIST_REF_FIELDS = ("additional_credentials_uid_refs",)


def _iter_refs(node: Any) -> Iterable[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _SCALAR_REF_FIELDS and isinstance(value, str):
                yield value
            elif key in _LIST_REF_FIELDS and isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        yield item
            else:
                yield from _iter_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_refs(item)


def build_graph(manifest: Manifest) -> nx.DiGraph:
    """Return a directed graph where ``A -> B`` means A depends on B."""
    graph: nx.DiGraph = nx.DiGraph()

    # track uid_ref -> kind for duplicate + missing checks
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

    data = manifest.model_dump(mode="python", exclude_none=True)

    def _owner_ref(container: dict[str, Any]) -> str | None:
        return container.get("uid_ref") if isinstance(container, dict) else None

    def _walk_collection(
        collection: list[dict[str, Any]], default_owner: str | None = None
    ) -> None:
        for item in collection or []:
            owner = _owner_ref(item) or default_owner
            if owner is None:
                continue
            for target in _iter_refs(item):
                if target not in owners:
                    raise RefError(
                        reason=f"reference to unknown uid_ref '{target}' from '{owner}'",
                        uid_ref=owner,
                        next_action="add the target object or fix the uid_ref",
                    )
                graph.add_edge(owner, target)

    _walk_collection(data.get("gateways") or [])
    _walk_collection(data.get("pam_configurations") or [])
    _walk_collection(data.get("projects") or [])
    # Resources: do not add resource -> nested-user edges for uid_refs that
    # already live under resources[].users[]. The resource block may still
    # reference those children (e.g. administrative_credentials_uid_ref); the
    # true create order is parent resource first, then nested pamUser rows.
    # Keeping those edges would invert order and can cycle with user -> parent.
    for item in data.get("resources") or []:
        owner = _owner_ref(item)
        if owner is None:
            continue
        nested_user_refs = frozenset(
            str(u["uid_ref"])
            for u in (item.get("users") or [])
            if isinstance(u, dict)
            and isinstance(u.get("uid_ref"), str)
            and str(u["uid_ref"]).strip()
        )
        for target in _iter_refs(item):
            if target in nested_user_refs:
                continue
            if target not in owners:
                raise RefError(
                    reason=f"reference to unknown uid_ref '{target}' from '{owner}'",
                    uid_ref=owner,
                    next_action="add the target object or fix the uid_ref",
                )
            graph.add_edge(owner, target)
    _walk_collection(data.get("users") or [])

    shared_folders = data.get("shared_folders") or {}
    sf_users_uid_ref = _owner_ref(shared_folders.get("users") or {})
    sf_resources_uid_ref = _owner_ref(shared_folders.get("resources") or {})

    for resource in data.get("resources") or []:
        shared_folder = resource.get("shared_folder")
        if shared_folder == "resources" and sf_resources_uid_ref in owners:
            graph.add_edge(resource["uid_ref"], sf_resources_uid_ref)
        elif shared_folder == "users" and sf_users_uid_ref in owners:
            graph.add_edge(resource["uid_ref"], sf_users_uid_ref)

    for user in data.get("users") or []:
        if user.get("shared_folder") == "users" and sf_users_uid_ref in owners:
            user_uid_ref = user.get("uid_ref")
            if user_uid_ref in owners:
                graph.add_edge(user_uid_ref, sf_users_uid_ref)

    # Nested pamUser rows are created under a parent resource: each user depends
    # on its parent (user_ref -> owner), not the reverse.
    for resource in data.get("resources") or []:
        owner = resource.get("uid_ref")
        for user in resource.get("users") or []:
            user_ref = user.get("uid_ref") or owner
            for target in _iter_refs(user):
                if target not in owners:
                    raise RefError(
                        reason=f"nested user references unknown uid_ref '{target}'",
                        uid_ref=user_ref,
                        next_action="fix the uid_ref or add the target",
                    )
                if user_ref:
                    graph.add_edge(user_ref, target)
            if owner and user_ref and user_ref in owners and user_ref != owner:
                graph.add_edge(user_ref, owner)

    return graph


def execution_order(graph: nx.DiGraph) -> list[str]:
    """Topological order for creates. Raises RefError on cycles."""
    try:
        # reverse because edges point from dependent to dependency
        order = list(nx.topological_sort(graph.reverse(copy=True)))
    except nx.NetworkXUnfeasible as exc:
        cycle = nx.find_cycle(graph)
        raise RefError(
            reason=f"dependency cycle detected: {cycle}",
            next_action="break the cycle by removing a reference",
        ) from exc
    return order
