"""Tests for keeper_sdk.core.msp_graph (P2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from keeper_sdk.core.errors import RefError
from keeper_sdk.core.manifest import load_declarative_manifest
from keeper_sdk.core.msp_graph import build_msp_graph, msp_apply_order
from keeper_sdk.core.msp_models import MspManifestV1

FIXTURES = Path(__file__).parent / "fixtures" / "examples" / "msp"


def _load(name: str) -> MspManifestV1:
    obj = load_declarative_manifest(FIXTURES / name)
    assert isinstance(obj, MspManifestV1)
    return obj


def test_minimal_graph_has_no_nodes() -> None:
    manifest = _load("01-minimal-msp.yaml")
    graph = build_msp_graph(manifest)
    assert list(graph.nodes()) == []
    assert list(graph.edges()) == []


def test_one_mc_graph_has_one_node() -> None:
    manifest = _load("02-msp-with-addons.yaml")
    graph = build_msp_graph(manifest)
    assert list(graph.nodes()) == ["Acme Widgets MC"]
    assert graph.nodes["Acme Widgets MC"]["kind"] == "managed_company"
    assert list(graph.edges()) == []


def test_multi_mc_graph_has_three_nodes_no_edges() -> None:
    manifest = _load("03-multi-mc-msp.yaml")
    graph = build_msp_graph(manifest)
    nodes = sorted(graph.nodes())
    assert nodes == ["Subsidiary A", "Subsidiary B", "Subsidiary C"]
    assert list(graph.edges()) == []


def test_apply_order_is_alphabetical() -> None:
    manifest = _load("03-multi-mc-msp.yaml")
    order = msp_apply_order(manifest)
    assert order == ["Subsidiary A", "Subsidiary B", "Subsidiary C"]


def test_apply_order_deterministic_across_input_order() -> None:
    """Manifest object built from same MCs in different order yields same apply order."""
    m1 = MspManifestV1.model_validate(
        {
            "schema": "msp-environment.v1",
            "name": "test",
            "managed_companies": [
                {"name": "Zebra", "plan": "business", "seats": 1},
                {"name": "Apple", "plan": "business", "seats": 1},
                {"name": "Mango", "plan": "business", "seats": 1},
            ],
        }
    )
    m2 = MspManifestV1.model_validate(
        {
            "schema": "msp-environment.v1",
            "name": "test",
            "managed_companies": [
                {"name": "Apple", "plan": "business", "seats": 1},
                {"name": "Mango", "plan": "business", "seats": 1},
                {"name": "Zebra", "plan": "business", "seats": 1},
            ],
        }
    )
    assert msp_apply_order(m1) == msp_apply_order(m2) == ["Apple", "Mango", "Zebra"]


def test_duplicate_mc_names_raise_ref_error() -> None:
    """Graph layer rejects duplicates even if semantic rules layer is skipped.

    The semantic-rules layer catches this earlier under validate_manifest, but
    build_msp_graph operates on an already-typed MspManifestV1 and must self-check.
    """
    manifest = MspManifestV1.model_validate(
        {
            "schema": "msp-environment.v1",
            "name": "dup-test",
            "managed_companies": [
                {"name": "Same", "plan": "business", "seats": 1},
                {"name": "Same", "plan": "businessPlus", "seats": 2},
            ],
        }
    )
    with pytest.raises(RefError, match="duplicate managed_company"):
        build_msp_graph(manifest)


def test_node_kind_attribute_is_managed_company() -> None:
    manifest = _load("03-multi-mc-msp.yaml")
    graph = build_msp_graph(manifest)
    for node in graph.nodes():
        assert graph.nodes[node]["kind"] == "managed_company"
