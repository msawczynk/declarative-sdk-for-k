"""keeper-vault.v1 dependency graph (PR-V2)."""

from __future__ import annotations

import pytest

from keeper_sdk.core.errors import RefError
from keeper_sdk.core.graph import execution_order
from keeper_sdk.core.vault_graph import (
    VAULT_FOLDER_NODE_PREFIX,
    build_vault_graph,
    vault_record_apply_order,
)
from keeper_sdk.core.vault_models import (
    VaultManifestV1,
    VaultRecord,
    load_vault_manifest,
)


def _login(uid: str, *, folder_ref: str | None = None) -> dict:
    row: dict = {"uid_ref": uid, "type": "login", "title": f"t-{uid}"}
    if folder_ref is not None:
        row["folder_ref"] = folder_ref
    return row


def test_build_vault_graph_empty() -> None:
    m = load_vault_manifest({"schema": "keeper-vault.v1", "records": []})
    g = build_vault_graph(m)
    assert g.number_of_nodes() == 0


def test_build_vault_graph_no_folder_no_edges() -> None:
    m = load_vault_manifest({"schema": "keeper-vault.v1", "records": [_login("a"), _login("b")]})
    g = build_vault_graph(m)
    assert g.number_of_nodes() == 2
    assert g.number_of_edges() == 0
    order = vault_record_apply_order(m)
    assert set(order) == {"a", "b"}


def test_duplicate_uid_ref() -> None:
    m = VaultManifestV1(
        records=[
            VaultRecord(uid_ref="dup", type="login", title="1"),
            VaultRecord(uid_ref="dup", type="login", title="2"),
        ]
    )
    with pytest.raises(RefError, match="duplicate uid_ref"):
        build_vault_graph(m)


def test_folder_ref_invalid_pattern() -> None:
    m = VaultManifestV1(
        records=[
            VaultRecord(
                uid_ref="r1",
                type="login",
                title="x",
                folder_ref="not-a-sharing-folder-ref",
            )
        ]
    )
    with pytest.raises(RefError, match="folder_ref must match"):
        build_vault_graph(m)


def test_folder_ref_synthetic_node_orders_before_records() -> None:
    folder = "keeper-vault-sharing:folders:sf-lab-001"
    m = load_vault_manifest(
        {
            "schema": "keeper-vault.v1",
            "records": [
                _login("rec-b", folder_ref=folder),
                _login("rec-a", folder_ref=folder),
            ],
        }
    )
    g = build_vault_graph(m)
    fid = f"{VAULT_FOLDER_NODE_PREFIX}{folder}"
    assert g.has_node(fid)
    assert g.has_edge("rec-a", fid)
    assert g.has_edge("rec-b", fid)
    full = execution_order(g)
    idx_folder = full.index(fid)
    assert full.index("rec-a") > idx_folder
    assert full.index("rec-b") > idx_folder
    rec_order = vault_record_apply_order(m)
    assert set(rec_order) == {"rec-a", "rec-b"}
