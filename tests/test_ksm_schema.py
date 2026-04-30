"""keeper-ksm.v1 offline schema, graph, diff, and CLI-capability tests."""

from __future__ import annotations

import json
from typing import Any

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CHANGES
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.errors import RefError, SchemaError
from keeper_sdk.core.ksm_diff import compute_ksm_diff
from keeper_sdk.core.ksm_graph import (
    KSM_CONFIG_OUTPUT_NODE_PREFIX,
    KSM_RECORD_NODE_PREFIX,
    KSM_SHARE_NODE_PREFIX,
    build_ksm_graph,
    ksm_apply_order,
)
from keeper_sdk.core.manifest import load_declarative_manifest_string
from keeper_sdk.core.models_ksm import KsmManifestV1, load_ksm_manifest
from keeper_sdk.core.schema import validate_manifest

APP_REF = "keeper-ksm:apps:app.api"
RECORD_REF = "keeper-vault:records:record.db"


def _minimal_doc() -> dict[str, Any]:
    return {
        "schema": "keeper-ksm.v1",
        "apps": [{"uid_ref": "app.api", "name": "API Service"}],
    }


def _full_doc() -> dict[str, Any]:
    return {
        "schema": "keeper-ksm.v1",
        "apps": [
            {
                "uid_ref": "app.api",
                "name": "API Service",
                "scopes": ["records:read", "records:update"],
                "allowed_ips": ["198.51.100.10/32"],
            }
        ],
        "tokens": [
            {
                "uid_ref": "token.api.bootstrap",
                "name": "bootstrap",
                "app_uid_ref": APP_REF,
                "one_time": True,
                "expiry": "2026-12-31T00:00:00Z",
            }
        ],
        "record_shares": [
            {
                "record_uid_ref": RECORD_REF,
                "app_uid_ref": APP_REF,
                "editable": True,
            }
        ],
        "config_outputs": [
            {
                "app_uid_ref": APP_REF,
                "format": "json",
                "output_path": "/tmp/ksm-config.json",
            }
        ],
    }


def _manifest(document: dict[str, Any] | None = None) -> KsmManifestV1:
    return load_ksm_manifest(document or _full_doc())


def test_ksm_v1_validate_empty_schema_for_back_compat() -> None:
    assert validate_manifest({"schema": "keeper-ksm.v1"}) == "keeper-ksm.v1"


def test_ksm_v1_validate_minimal_one_app() -> None:
    assert validate_manifest(_minimal_doc()) == "keeper-ksm.v1"


def test_ksm_v1_validate_full() -> None:
    assert validate_manifest(_full_doc()) == "keeper-ksm.v1"


def test_ksm_v1_invalid_missing_required_field() -> None:
    document = _minimal_doc()
    del document["apps"][0]["name"]

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert exc.value.context["location"] == "apps/0"
    assert "name" in exc.value.reason


def test_ksm_v1_rejects_bad_uid_ref_pattern() -> None:
    document = _minimal_doc()
    document["apps"][0]["uid_ref"] = "_bad"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "does not match" in exc.value.reason


def test_ksm_v1_rejects_bad_app_reference_pattern() -> None:
    document = _full_doc()
    document["tokens"][0]["app_uid_ref"] = "app.api"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "does not match" in exc.value.reason


def test_ksm_v1_rejects_unknown_top_level_field() -> None:
    document = _minimal_doc()
    document["ksm_apps"] = []

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "Additional properties" in exc.value.reason


def test_ksm_manifest_loader_returns_typed_model() -> None:
    loaded = load_declarative_manifest_string(json.dumps(_minimal_doc()), suffix=".json")

    assert isinstance(loaded, KsmManifestV1)
    assert loaded.apps[0].name == "API Service"


def test_ksm_manifest_roundtrip() -> None:
    manifest = _manifest()
    dumped = manifest.model_dump(mode="json", exclude_none=True, by_alias=True)
    loaded = load_declarative_manifest_string(json.dumps(dumped), suffix=".json")

    assert isinstance(loaded, KsmManifestV1)
    assert loaded.model_dump(mode="json", exclude_none=True, by_alias=True) == dumped


def test_ksm_graph_builds_app_token_dependency() -> None:
    graph = build_ksm_graph(_manifest())

    assert graph.has_edge("token.api.bootstrap", "app.api")
    assert graph.nodes["app.api"]["kind"] == "ksm_app"


def test_ksm_graph_builds_share_and_config_dependencies() -> None:
    graph = build_ksm_graph(_manifest())
    share_node = next(node for node in graph if str(node).startswith(KSM_SHARE_NODE_PREFIX))
    output_node = next(
        node for node in graph if str(node).startswith(KSM_CONFIG_OUTPUT_NODE_PREFIX)
    )
    record_node = next(node for node in graph if str(node).startswith(KSM_RECORD_NODE_PREFIX))

    assert graph.has_edge(share_node, "app.api")
    assert graph.has_edge(share_node, record_node)
    assert graph.has_edge(output_node, "app.api")


def test_ksm_graph_rejects_unknown_app_reference() -> None:
    document = _full_doc()
    document["tokens"][0]["app_uid_ref"] = "keeper-ksm:apps:app.missing"
    manifest = _manifest(document)

    with pytest.raises(RefError) as exc:
        build_ksm_graph(manifest)

    assert "unknown KSM app" in exc.value.reason


def test_ksm_graph_rejects_duplicate_uid_refs() -> None:
    document = _full_doc()
    document["tokens"][0]["uid_ref"] = "app.api"

    with pytest.raises(SchemaError) as exc:
        load_ksm_manifest(document)

    assert "duplicate uid_ref" in exc.value.reason


def test_ksm_apply_order_places_app_before_dependents() -> None:
    order = ksm_apply_order(_manifest())
    share_node = next(node for node in order if str(node).startswith(KSM_SHARE_NODE_PREFIX))
    output_node = next(
        node for node in order if str(node).startswith(KSM_CONFIG_OUTPUT_NODE_PREFIX)
    )

    assert order.index("app.api") < order.index("token.api.bootstrap")
    assert order.index("app.api") < order.index(share_node)
    assert order.index("app.api") < order.index(output_node)
    assert all(not node.startswith(KSM_RECORD_NODE_PREFIX) for node in order)


def test_ksm_diff_creates_all_objects_when_live_empty() -> None:
    changes = compute_ksm_diff(_manifest(), {})

    assert {change.kind for change in changes} == {ChangeKind.CREATE}
    assert len(changes) == 4


def test_ksm_diff_noops_matching_snapshot() -> None:
    manifest = _manifest()
    live = manifest.model_dump(mode="python", exclude_none=True, by_alias=True)

    changes = compute_ksm_diff(manifest, live)

    assert {change.kind for change in changes} == {ChangeKind.NOOP}


def test_ksm_diff_detects_scope_change() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["apps"][0]["scopes"] = ["records:read"]

    changes = compute_ksm_diff(desired, live)
    app_change = next(change for change in changes if change.uid_ref == "app.api")

    assert app_change.kind is ChangeKind.UPDATE
    assert app_change.before == {"scopes": ["records:read"]}
    assert app_change.after == {"scopes": ["records:read", "records:update"]}


def test_ksm_diff_detects_new_token() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["tokens"] = []

    changes = compute_ksm_diff(desired, live)
    token_change = next(change for change in changes if change.uid_ref == "token.api.bootstrap")

    assert token_change.kind is ChangeKind.CREATE
    assert token_change.resource_type == "ksm_token"


def test_ksm_diff_detects_removed_share_when_delete_allowed() -> None:
    desired = _manifest(_minimal_doc())
    live = _full_doc()

    changes = compute_ksm_diff(desired, live, allow_delete=True)
    share_delete = next(change for change in changes if change.resource_type == "ksm_record_share")

    assert share_delete.kind is ChangeKind.DELETE
    assert share_delete.before["record_uid_ref"] == RECORD_REF


def test_ksm_plan_mock_provider_supported(tmp_path) -> None:
    manifest = tmp_path / "ksm.yaml"
    manifest.write_text(
        """\
schema: keeper-ksm.v1
apps:
  - uid_ref: app.api
    name: API Service
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        main,
        ["--provider", "mock", "plan", str(manifest), "--json"],
        catch_exceptions=False,
    )

    assert result.exit_code == EXIT_CHANGES, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["create"] == 1
    assert payload["changes"][0]["resource_type"] == "ksm_app"
