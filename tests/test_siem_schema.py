"""keeper-siem.v1 offline schema, model, diff, and CLI tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.manifest import load_declarative_manifest_string
from keeper_sdk.core.models_siem import SIEM_FAMILY, SiemManifestV1, load_siem_manifest
from keeper_sdk.core.schema import load_schema_for_family, validate_manifest
from keeper_sdk.core.siem_diff import compute_siem_diff


def _minimal_doc() -> dict[str, Any]:
    return {
        "schema": SIEM_FAMILY,
    }


def _full_doc() -> dict[str, Any]:
    return {
        "schema": SIEM_FAMILY,
        "name": "acme-siem",
        "manager": "keeper-dsk",
        "sinks": [
            {
                "uid_ref": "sink.splunk",
                "name": "Splunk prod HEC",
                "type": "splunk",
                "endpoint": "https://splunk.example.com:8088/services/collector",
                "token": "keeper-vault:records:rec.splunk-hec-token",
                "filter": {
                    "event_types": ["record_delete", "login_failure"],
                    "severity_min": "medium",
                },
                "batch_size": 1000,
                "flush_interval_sec": 15,
            },
            {
                "uid_ref": "sink.datadog",
                "name": "Datadog security intake",
                "type": "datadog",
                "endpoint": "https://http-intake.logs.datadoghq.com/api/v2/logs",
                "token": "keeper-vault:records:rec.datadog-api-key",
            },
        ],
        "routes": [
            {
                "uid_ref": "route.security",
                "event_type_patterns": ["login_*", "record_*"],
                "sink_uid_refs": ["sink.splunk", "sink.datadog"],
            }
        ],
    }


def _manifest(document: dict[str, Any] | None = None) -> SiemManifestV1:
    return load_siem_manifest(copy.deepcopy(document or _full_doc()))


def _write_manifest(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "siem.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_siem_v1_schema_is_packaged_under_keeper_siem_path() -> None:
    schema = load_schema_for_family(SIEM_FAMILY)

    assert schema["title"] == SIEM_FAMILY
    assert schema["properties"]["schema"]["const"] == SIEM_FAMILY
    assert schema["x-keeper-live-proof"]["status"] == "upstream-gap"
    assert "sinks" in schema["properties"]
    assert "routes" in schema["properties"]


def test_siem_v1_validate_minimal_schema_only() -> None:
    assert validate_manifest(_minimal_doc()) == SIEM_FAMILY


def test_siem_v1_validate_full() -> None:
    assert validate_manifest(_full_doc()) == SIEM_FAMILY


def test_siem_v1_invalid_sink_type_enum() -> None:
    document = _full_doc()
    document["sinks"][0]["type"] = "syslog"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "not one of" in exc.value.reason


@pytest.mark.parametrize("missing_field", ["uid_ref", "name", "type", "endpoint"])
def test_siem_v1_sink_rejects_missing_required(missing_field: str) -> None:
    document = _full_doc()
    del document["sinks"][0][missing_field]

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert exc.value.context["location"] == "sinks/0"
    assert missing_field in exc.value.reason


def test_siem_v1_invalid_token_must_be_vault_record_ref() -> None:
    document = _full_doc()
    document["sinks"][0]["token"] = "raw-token-value"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert exc.value.context["location"] == "sinks/0/token"


def test_siem_loader_returns_typed_model_with_sink_defaults() -> None:
    document = _full_doc()
    del document["sinks"][1]["token"]

    loaded = load_declarative_manifest_string(json.dumps(document), suffix=".json")

    assert isinstance(loaded, SiemManifestV1)
    assert loaded.sinks[1].batch_size == 500
    assert loaded.sinks[1].flush_interval_sec == 30
    assert loaded.sinks[1].token is None


def test_siem_manifest_roundtrip() -> None:
    manifest = _manifest()
    dumped = manifest.model_dump(mode="json", exclude_none=True, by_alias=True)
    loaded = load_declarative_manifest_string(json.dumps(dumped), suffix=".json")

    assert isinstance(loaded, SiemManifestV1)
    assert loaded.model_dump(mode="json", exclude_none=True, by_alias=True) == dumped


def test_siem_loader_rejects_duplicate_uid_refs() -> None:
    document = _full_doc()
    document["routes"][0]["uid_ref"] = "sink.splunk"

    with pytest.raises(SchemaError) as exc:
        load_siem_manifest(document)

    assert "duplicate uid_ref" in exc.value.reason
    assert "sink.splunk" in exc.value.reason


def test_siem_loader_rejects_unknown_route_sink_ref() -> None:
    document = _full_doc()
    document["routes"][0]["sink_uid_refs"] = ["sink.missing"]

    with pytest.raises(SchemaError) as exc:
        load_siem_manifest(document)

    assert "unknown route sink_uid_refs" in exc.value.reason
    assert "sink.missing" in exc.value.reason


def test_siem_diff_detects_sink_add() -> None:
    row = next(
        change
        for change in compute_siem_diff(_manifest(_full_doc()), {"sinks": []})
        if change.resource_type == "siem_sink" and change.uid_ref == "sink.splunk"
    )

    assert row.kind is ChangeKind.CREATE
    assert row.after["type"] == "splunk"
    assert row.after["token"] == "keeper-vault:records:rec.splunk-hec-token"


def test_siem_diff_detects_sink_endpoint_change() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["sinks"][0]["endpoint"] = "https://old-splunk.example.com/services/collector"

    row = next(
        change for change in compute_siem_diff(desired, live) if change.uid_ref == "sink.splunk"
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.before == {"endpoint": "https://old-splunk.example.com/services/collector"}
    assert row.after == {"endpoint": "https://splunk.example.com:8088/services/collector"}


def test_siem_diff_detects_route_change() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["routes"][0]["sink_uid_refs"] = ["sink.splunk"]

    row = next(
        change for change in compute_siem_diff(desired, live) if change.uid_ref == "route.security"
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.before == {"sink_uid_refs": ["sink.splunk"]}
    assert row.after == {"sink_uid_refs": ["sink.datadog", "sink.splunk"]}


def test_siem_diff_noops_matching_snapshot_with_order_insensitive_lists() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["sinks"][0]["filter"]["event_types"] = ["login_failure", "record_delete"]
    live["routes"][0]["sink_uid_refs"] = ["sink.datadog", "sink.splunk"]

    changes = compute_siem_diff(desired, live)

    assert {change.kind for change in changes} == {ChangeKind.NOOP}


def test_siem_diff_skips_unmanaged_live_by_default() -> None:
    desired = _manifest(_minimal_doc())
    live = {
        "sinks": [
            {
                "uid_ref": "sink.legacy",
                "name": "Legacy webhook",
                "type": "webhook",
                "endpoint": "https://hooks.example.com/legacy",
            }
        ]
    }

    row = compute_siem_diff(desired, live)[0]

    assert row.kind is ChangeKind.SKIP
    assert row.reason == "unmanaged SIEM object; pass allow_delete=True to remove"


def test_siem_diff_deletes_unmanaged_live_when_allowed() -> None:
    desired = _manifest(_minimal_doc())
    live = {
        "routes": [
            {
                "uid_ref": "route.legacy",
                "event_type_patterns": ["record_*"],
                "sink_uid_refs": ["sink.legacy"],
            }
        ]
    }

    row = compute_siem_diff(desired, live, allow_delete=True)[0]

    assert row.kind is ChangeKind.DELETE
    assert row.reason is None


def test_siem_diff_detects_duplicate_live_key_conflict() -> None:
    desired = _manifest(_minimal_doc())
    live = {
        "sinks": [
            {
                "uid_ref": "sink.dup",
                "name": "Webhook A",
                "type": "webhook",
                "endpoint": "https://hooks.example.com/a",
            },
            {
                "uid_ref": "sink.dup",
                "name": "Webhook B",
                "type": "webhook",
                "endpoint": "https://hooks.example.com/b",
            },
        ]
    }

    row = compute_siem_diff(desired, live)[0]

    assert row.kind is ChangeKind.CONFLICT
    assert row.reason == "duplicate live SIEM object key: sinks:sink.dup"


def test_siem_validate_cli_is_schema_only(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _minimal_doc())

    result = CliRunner().invoke(main, ["validate", str(path), "--json"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["family"] == SIEM_FAMILY
    assert payload["mode"] == "schema_only"


def test_siem_plan_cli_exits_capability_error(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _full_doc())

    result = CliRunner().invoke(main, ["plan", str(path), "--json"], catch_exceptions=False)

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert SIEM_FAMILY in result.output
    assert "upstream-gap" in result.output


def test_siem_apply_cli_exits_capability_error(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _full_doc())

    result = CliRunner().invoke(main, ["apply", str(path), "--dry-run"], catch_exceptions=False)

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert SIEM_FAMILY in result.output
    assert "upstream-gap" in result.output
