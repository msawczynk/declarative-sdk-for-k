"""keeper-enterprise.v1 offline schema, graph, diff, and plan tests."""

from __future__ import annotations

import json
from typing import Any

import pytest

from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.enterprise_diff import compute_enterprise_diff
from keeper_sdk.core.enterprise_graph import build_enterprise_graph, enterprise_apply_order
from keeper_sdk.core.errors import RefError, SchemaError
from keeper_sdk.core.manifest import load_declarative_manifest_string
from keeper_sdk.core.models_enterprise import EnterpriseManifestV1, load_enterprise_manifest
from keeper_sdk.core.planner import build_plan
from keeper_sdk.core.schema import validate_manifest


def _minimal_doc() -> dict[str, Any]:
    return {
        "schema": "keeper-enterprise.v1",
        "nodes": [{"uid_ref": "node.root", "name": "Root"}],
        "users": [
            {
                "uid_ref": "user.alice",
                "email": "alice@example.com",
                "node_uid_ref": "keeper-enterprise:nodes:node.root",
            }
        ],
    }


def _full_doc() -> dict[str, Any]:
    return {
        "schema": "keeper-enterprise.v1",
        "nodes": [
            {"uid_ref": "node.root", "name": "Root"},
            {
                "uid_ref": "node.eng",
                "name": "Engineering",
                "parent_uid_ref": "keeper-enterprise:nodes:node.root",
            },
        ],
        "users": [
            {
                "uid_ref": "user.alice",
                "email": "alice@example.com",
                "name": "Alice Example",
                "node_uid_ref": "keeper-enterprise:nodes:node.eng",
                "status": "active",
                "lock_status": "unlocked",
                "pending_approval": False,
            },
            {
                "uid_ref": "user.bob",
                "email": "bob@example.com",
                "node_uid_ref": "keeper-enterprise:nodes:node.eng",
            },
        ],
        "roles": [
            {
                "uid_ref": "role.platform",
                "name": "Platform Admin",
                "node_uid_ref": "keeper-enterprise:nodes:node.eng",
                "user_uid_refs": ["keeper-enterprise:users:user.alice"],
                "visible_below": True,
                "new_user_inherit": False,
                "manage_nodes": True,
            }
        ],
        "teams": [
            {
                "uid_ref": "team.platform",
                "name": "Platform",
                "node_uid_ref": "keeper-enterprise:nodes:node.eng",
                "role_uid_refs": ["keeper-enterprise:roles:role.platform"],
                "user_uid_refs": [
                    "keeper-enterprise:users:user.alice",
                    "keeper-enterprise:users:user.bob",
                ],
                "restrict_edit": True,
                "restrict_share": False,
                "restrict_view": False,
            }
        ],
        "enforcements": [
            {
                "uid_ref": "enforce.2fa",
                "role_uid_ref": "keeper-enterprise:roles:role.platform",
                "key": "require_two_factor",
                "value": True,
            }
        ],
        "aliases": [
            {
                "uid_ref": "alias.alice",
                "user_uid_ref": "keeper-enterprise:users:user.alice",
                "email": "a.example@example.com",
            }
        ],
    }


def _manifest(document: dict[str, Any] | None = None) -> EnterpriseManifestV1:
    return load_enterprise_manifest(document or _full_doc())


def test_enterprise_v1_validate_minimal() -> None:
    assert validate_manifest(_minimal_doc()) == "keeper-enterprise.v1"


def test_enterprise_v1_validate_full() -> None:
    assert validate_manifest(_full_doc()) == "keeper-enterprise.v1"


def test_enterprise_v1_invalid_missing_required_field() -> None:
    document = _minimal_doc()
    del document["users"][0]["email"]

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert exc.value.context["location"] == "users/0"
    assert "email" in exc.value.reason


def test_enterprise_v1_rejects_bad_uid_ref_pattern() -> None:
    document = _minimal_doc()
    document["nodes"][0]["uid_ref"] = "_bad"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "does not match" in exc.value.reason


def test_enterprise_v1_rejects_unknown_top_level_field() -> None:
    document = _minimal_doc()
    document["role_assignments"] = []

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "Additional properties" in exc.value.reason


def test_enterprise_manifest_loader_returns_typed_model() -> None:
    loaded = load_declarative_manifest_string(json.dumps(_minimal_doc()), suffix=".json")

    assert isinstance(loaded, EnterpriseManifestV1)
    assert loaded.users[0].email == "alice@example.com"


def test_enterprise_manifest_roundtrip() -> None:
    manifest = _manifest()
    dumped = manifest.model_dump(mode="json", exclude_none=True, by_alias=True)
    loaded = load_declarative_manifest_string(json.dumps(dumped), suffix=".json")

    assert isinstance(loaded, EnterpriseManifestV1)
    assert loaded.model_dump(mode="json", exclude_none=True, by_alias=True) == dumped


def test_enterprise_graph_builds_node_hierarchy() -> None:
    graph = build_enterprise_graph(_manifest())

    assert graph.has_edge("node.eng", "node.root")
    assert graph.nodes["node.root"]["kind"] == "enterprise_node"


def test_enterprise_graph_wires_team_role_user_refs() -> None:
    graph = build_enterprise_graph(_manifest())

    assert graph.has_edge("team.platform", "role.platform")
    assert graph.has_edge("role.platform", "user.alice")
    assert graph.has_edge("team.platform", "user.bob")


def test_enterprise_graph_rejects_unknown_reference() -> None:
    document = _full_doc()
    document["teams"][0]["role_uid_refs"] = ["keeper-enterprise:roles:role.missing"]
    manifest = _manifest(document)

    with pytest.raises(RefError) as exc:
        build_enterprise_graph(manifest)

    assert "unknown uid_ref" in exc.value.reason


def test_enterprise_graph_rejects_duplicate_uid_refs() -> None:
    document = _full_doc()
    document["aliases"][0]["uid_ref"] = "user.alice"

    with pytest.raises(SchemaError) as exc:
        load_enterprise_manifest(document)

    assert "duplicate uid_ref" in exc.value.reason


def test_enterprise_apply_order_places_dependencies_first() -> None:
    order = enterprise_apply_order(_manifest())

    assert order.index("node.root") < order.index("node.eng")
    assert order.index("user.alice") < order.index("role.platform")
    assert order.index("role.platform") < order.index("team.platform")


def test_enterprise_diff_creates_all_objects_when_live_empty() -> None:
    changes = compute_enterprise_diff(_manifest(), {})

    assert {change.kind for change in changes} == {ChangeKind.CREATE}
    assert len(changes) == 8


def test_enterprise_diff_noops_matching_snapshot() -> None:
    manifest = _manifest()
    live = manifest.model_dump(mode="python", exclude_none=True, by_alias=True)

    changes = compute_enterprise_diff(manifest, live)

    assert {change.kind for change in changes} == {ChangeKind.NOOP}


def test_enterprise_diff_detects_user_role_change() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["roles"][0]["user_uid_refs"] = []

    changes = compute_enterprise_diff(desired, live)
    role_change = next(change for change in changes if change.uid_ref == "role.platform")

    assert role_change.kind is ChangeKind.UPDATE
    assert role_change.before == {"user_uid_refs": []}
    assert role_change.after == {
        "user_uid_refs": ["keeper-enterprise:users:user.alice"],
    }


def test_enterprise_diff_detects_team_membership_change() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["teams"][0]["user_uid_refs"] = ["keeper-enterprise:users:user.alice"]

    changes = compute_enterprise_diff(desired, live)
    team_change = next(change for change in changes if change.uid_ref == "team.platform")

    assert team_change.kind is ChangeKind.UPDATE
    assert team_change.before == {
        "user_uid_refs": ["keeper-enterprise:users:user.alice"],
    }
    assert team_change.after == {
        "user_uid_refs": [
            "keeper-enterprise:users:user.alice",
            "keeper-enterprise:users:user.bob",
        ],
    }


def test_enterprise_diff_skips_unmanaged_live_objects_without_allow_delete() -> None:
    changes = compute_enterprise_diff(_manifest(_minimal_doc()), _full_doc())
    skipped = [change for change in changes if change.kind is ChangeKind.SKIP]

    assert {change.uid_ref for change in skipped} == {
        "node.eng",
        "role.platform",
        "team.platform",
        "enforce.2fa",
        "alias.alice",
        "user.bob",
    }


def test_enterprise_plan_uses_graph_order() -> None:
    manifest = _manifest()
    plan = build_plan(
        "enterprise",
        compute_enterprise_diff(manifest, {}),
        enterprise_apply_order(manifest),
    )

    ordered = [change.uid_ref for change in plan.ordered()]
    assert ordered.index("node.root") < ordered.index("node.eng")
    assert ordered.index("role.platform") < ordered.index("team.platform")
