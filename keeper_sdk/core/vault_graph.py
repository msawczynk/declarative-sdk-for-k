"""Dependency graph for ``keeper-vault.v1`` manifests (PR-V2).

Convention matches :mod:`keeper_sdk.core.graph`: a directed edge ``A -> B`` means
**A depends on B** — B is a prerequisite of A. :func:`execution_order` therefore
lists ``B`` before ``A``.

``folder_ref`` values use the cross-family ``keeper-vault-sharing:folders:...``
form from the packaged schema. They are modeled as **synthetic** graph nodes
(prefix :data:`VAULT_FOLDER_NODE_PREFIX`) so topological order reflects
"folder context before records that declare it". Those node ids are not valid
manifest ``uid_ref`` values (schema requires an alphanumeric first character).

Callers that only apply vault records should use :func:`vault_record_apply_order`
to drop synthetic nodes while preserving dependency order among real records.
"""

from __future__ import annotations

import re

import networkx as nx

from keeper_sdk.core.errors import RefError
from keeper_sdk.core.graph import execution_order
from keeper_sdk.core.vault_models import VaultManifestV1

# Synthetic folder nodes; first char '_' is invalid for schema uid_ref.
VAULT_FOLDER_NODE_PREFIX = "_vault_folder:"

_FOLDER_REF_PATTERN = re.compile(r"^keeper-vault-sharing:folders:.+$")


def _folder_graph_id(folder_ref: str) -> str:
    return f"{VAULT_FOLDER_NODE_PREFIX}{folder_ref}"


def build_vault_graph(manifest: VaultManifestV1) -> nx.DiGraph:
    """Return a directed graph over record ``uid_ref`` nodes and folder prerequisites.

    Raises :class:`RefError` on duplicate ``uid_ref`` or invalid ``folder_ref``.
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

    for rec in manifest.records:
        fr = rec.folder_ref
        if fr is None or not str(fr).strip():
            continue
        folder_ref = str(fr).strip()
        if not _FOLDER_REF_PATTERN.match(folder_ref):
            raise RefError(
                reason=(
                    "folder_ref must match keeper-vault-sharing:folders:... "
                    f"(L1); got {folder_ref!r}"
                ),
                uid_ref=rec.uid_ref,
                next_action="fix folder_ref or omit it until sharing scope lands",
            )
        fid = _folder_graph_id(folder_ref)
        if fid not in graph:
            graph.add_node(fid, kind="folder_ref")
        graph.add_edge(rec.uid_ref, fid)

    return graph


def vault_record_apply_order(manifest: VaultManifestV1) -> list[str]:
    """Topological order of **record** ``uid_ref`` values (synthetic folder nodes removed).

    Raises :class:`RefError` from :func:`build_vault_graph` or :func:`execution_order`
    (e.g. duplicate ``uid_ref``; cycles cannot occur with current edge rules).
    """
    graph = build_vault_graph(manifest)
    full = execution_order(graph)
    return [n for n in full if not n.startswith(VAULT_FOLDER_NODE_PREFIX)]
