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


def test_graph_places_shared_folder_before_resource(full_local_manifest_path: Path) -> None:
    manifest = load_manifest(full_local_manifest_path)
    graph = build_graph(manifest)
    order = execution_order(graph)

    shared_folder_idx = order.index("acme-prod-sf-resources")
    resource_indexes = [
        order.index(resource.uid_ref)
        for resource in manifest.resources
        if getattr(resource, "shared_folder", None) == "resources"
    ]

    assert resource_indexes
    assert all(shared_folder_idx < resource_idx for resource_idx in resource_indexes)


def test_cycle_detected() -> None:
    """execution_order must reject cycles."""
    import networkx as nx

    graph: nx.DiGraph = nx.DiGraph()
    graph.add_edge("a", "b")
    graph.add_edge("b", "a")
    with pytest.raises(RefError):
        execution_order(graph)


def test_nested_pam_user_is_ordered_after_parent_resource(tmp_path: Path) -> None:
    """resources[].users[] must not invert dependency (parent before nested pamUser)."""
    import yaml

    document = {
        "version": "1",
        "name": "g-nested-order",
        "shared_folders": {
            "resources": {
                "uid_ref": "sf-res",
                "manage_users": True,
                "manage_records": True,
                "can_edit": True,
                "can_share": True,
            }
        },
        "gateways": [{"uid_ref": "gw-1", "name": "GW", "mode": "reference_existing"}],
        "pam_configurations": [
            {"uid_ref": "cfg-1", "environment": "local", "title": "Cfg", "gateway_uid_ref": "gw-1"}
        ],
        "resources": [
            {
                "uid_ref": "host-1",
                "type": "pamMachine",
                "title": "linux-1",
                "pam_configuration_uid_ref": "cfg-1",
                "shared_folder": "resources",
                "host": "10.0.0.1",
                "port": "22",
                "ssl_verification": True,
                "operating_system": "Linux",
                "pam_settings": {
                    "connection": {
                        "protocol": "ssh",
                        "port": "22",
                        "administrative_credentials_uid_ref": "nested-user-1",
                    }
                },
                "users": [
                    {
                        "uid_ref": "nested-user-1",
                        "type": "pamUser",
                        "title": "u1",
                        "login": "root",
                    }
                ],
            }
        ],
    }
    path = tmp_path / "nested-order.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    manifest = load_manifest(path)
    order = execution_order(build_graph(manifest))
    assert order.index("host-1") < order.index("nested-user-1")
