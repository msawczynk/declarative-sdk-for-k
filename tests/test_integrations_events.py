"""keeper-integrations-events.v1 offline schema, model, diff, and CLI tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.integrations_events_diff import compute_events_diff
from keeper_sdk.core.manifest import load_declarative_manifest_string
from keeper_sdk.core.models_integrations_events import (
    EVENTS_FAMILY,
    EventsManifestV1,
    load_events_manifest,
)
from keeper_sdk.core.schema import load_schema_for_family, validate_manifest


def _minimal_doc() -> dict[str, Any]:
    return {
        "schema": EVENTS_FAMILY,
        "name": "acme-events",
    }


def _full_doc() -> dict[str, Any]:
    return {
        "schema": EVENTS_FAMILY,
        "name": "acme-events",
        "manager": "keeper-dsk",
        "automator_rules": [
            {
                "uid_ref": "rule.login",
                "name": "Login webhook",
                "trigger": "login",
                "action": "webhook",
                "endpoint_uid_ref": "endpoint.webhook",
                "filter_tags": ["prod", "admin"],
            }
        ],
        "audit_alerts": [
            {
                "uid_ref": "alert.critical",
                "name": "Critical alerts",
                "event_types": ["login_failure", "record_delete"],
                "severity": "critical",
                "notify_emails": ["secops@example.com"],
            }
        ],
        "api_keys": [
            {
                "uid_ref": "api.reporting",
                "name": "Reporting API",
                "scopes": ["events:read", "audit:read"],
                "expiry_days": 90,
                "ip_allowlist": ["203.0.113.10"],
            }
        ],
        "event_routes": [
            {
                "uid_ref": "route.siem",
                "name": "SIEM route",
                "destination_type": "siem",
                "destination_uid_ref": "siem.splunk",
                "filter_severity": "high",
            }
        ],
    }


def _manifest(document: dict[str, Any] | None = None) -> EventsManifestV1:
    return load_events_manifest(document or _full_doc())


def _write_manifest(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "events.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_events_v1_schema_is_packaged_under_integrations_path() -> None:
    schema = load_schema_for_family(EVENTS_FAMILY)

    assert schema["title"] == EVENTS_FAMILY
    assert "event_routes" in schema["properties"]


def test_events_v1_validate_minimal_name_only() -> None:
    assert validate_manifest(_minimal_doc()) == EVENTS_FAMILY


def test_events_v1_validate_full() -> None:
    assert validate_manifest(_full_doc()) == EVENTS_FAMILY


def test_events_v1_invalid_missing_manifest_name() -> None:
    document = _minimal_doc()
    del document["name"]

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert exc.value.context["location"] == "<root>"
    assert "name" in exc.value.reason


def test_events_v1_invalid_missing_automator_endpoint_ref() -> None:
    document = _full_doc()
    del document["automator_rules"][0]["endpoint_uid_ref"]

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert exc.value.context["location"] == "automator_rules/0"
    assert "endpoint_uid_ref" in exc.value.reason


def test_events_v1_invalid_automator_trigger_enum() -> None:
    document = _full_doc()
    document["automator_rules"][0]["trigger"] = "record_delete"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "not one of" in exc.value.reason


def test_events_v1_invalid_audit_severity_enum() -> None:
    document = _full_doc()
    document["audit_alerts"][0]["severity"] = "blocker"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "not one of" in exc.value.reason


def test_events_v1_invalid_api_key_expiry_minimum() -> None:
    document = _full_doc()
    document["api_keys"][0]["expiry_days"] = 0

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "minimum" in exc.value.reason


def test_events_v1_invalid_event_route_destination_type() -> None:
    document = _full_doc()
    document["event_routes"][0]["destination_type"] = "syslog"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "not one of" in exc.value.reason


def test_events_v1_rejects_unknown_top_level_property() -> None:
    document = _minimal_doc()
    document["extra"] = True

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "Additional properties" in exc.value.reason


def test_events_loader_returns_typed_model_with_defaults() -> None:
    document = _full_doc()
    del document["audit_alerts"][0]["severity"]
    del document["api_keys"][0]["scopes"]

    loaded = load_declarative_manifest_string(json.dumps(document), suffix=".json")

    assert isinstance(loaded, EventsManifestV1)
    assert loaded.audit_alerts[0].severity == "medium"
    assert loaded.api_keys[0].scopes == []


def test_events_manifest_roundtrip() -> None:
    manifest = _manifest()
    dumped = manifest.model_dump(mode="json", exclude_none=True, by_alias=True)
    loaded = load_declarative_manifest_string(json.dumps(dumped), suffix=".json")

    assert isinstance(loaded, EventsManifestV1)
    assert loaded.model_dump(mode="json", exclude_none=True, by_alias=True) == dumped


def test_events_loader_rejects_duplicate_uid_refs() -> None:
    document = _full_doc()
    document["event_routes"][0]["uid_ref"] = "api.reporting"

    with pytest.raises(SchemaError) as exc:
        load_events_manifest(document)

    assert "duplicate uid_ref" in exc.value.reason


def test_events_loader_rejects_bad_notify_email() -> None:
    document = _full_doc()
    document["audit_alerts"][0]["notify_emails"] = ["not-an-email"]

    with pytest.raises(SchemaError) as exc:
        load_events_manifest(document)

    assert "notify_emails" in exc.value.reason


def test_events_diff_detects_automator_rule_add() -> None:
    row = next(
        change
        for change in compute_events_diff(_manifest(_full_doc()), {"automator_rules": []})
        if change.resource_type == "events_automator_rule"
    )

    assert row.kind is ChangeKind.CREATE
    assert row.uid_ref == "rule.login"
    assert row.after["trigger"] == "login"


def test_events_diff_detects_audit_alert_change() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["audit_alerts"][0]["severity"] = "medium"

    row = next(
        change
        for change in compute_events_diff(desired, live)
        if change.uid_ref == "alert.critical"
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.before == {"severity": "medium"}
    assert row.after == {"severity": "critical"}


def test_events_diff_detects_api_key_ip_allowlist_change() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["api_keys"][0]["ip_allowlist"] = ["198.51.100.10"]

    row = next(
        change for change in compute_events_diff(desired, live) if change.uid_ref == "api.reporting"
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.before == {"ip_allowlist": ["198.51.100.10"]}
    assert row.after == {"ip_allowlist": ["203.0.113.10"]}


def test_events_diff_detects_event_route_change() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["event_routes"][0]["destination_uid_ref"] = "siem.old"

    row = next(
        change for change in compute_events_diff(desired, live) if change.uid_ref == "route.siem"
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.before == {"destination_uid_ref": "siem.old"}
    assert row.after == {"destination_uid_ref": "siem.splunk"}


def test_events_diff_noops_matching_snapshot() -> None:
    manifest = _manifest()
    live = manifest.model_dump(mode="python", exclude_none=True, by_alias=True)

    changes = compute_events_diff(manifest, live)

    assert {change.kind for change in changes} == {ChangeKind.NOOP}


def test_events_diff_skips_unmanaged_live_by_default() -> None:
    desired = _manifest(_minimal_doc())
    live = {
        "api_keys": [
            {
                "uid_ref": "api.legacy",
                "name": "Legacy API",
            }
        ]
    }

    row = compute_events_diff(desired, live)[0]

    assert row.kind is ChangeKind.SKIP
    assert row.reason == "unmanaged events object; pass allow_delete=True to remove"


def test_events_diff_deletes_unmanaged_live_when_allowed() -> None:
    desired = _manifest(_minimal_doc())
    live = {
        "api_keys": [
            {
                "uid_ref": "api.legacy",
                "name": "Legacy API",
            }
        ]
    }

    row = compute_events_diff(desired, live, allow_delete=True)[0]

    assert row.kind is ChangeKind.DELETE
    assert row.reason is None


def test_events_diff_detects_duplicate_live_key_conflict() -> None:
    desired = _manifest(_minimal_doc())
    live = {
        "event_routes": [
            {
                "uid_ref": "route.dup",
                "name": "Route A",
                "destination_type": "webhook",
                "destination_uid_ref": "hook.a",
            },
            {
                "uid_ref": "route.dup",
                "name": "Route B",
                "destination_type": "webhook",
                "destination_uid_ref": "hook.b",
            },
        ]
    }

    row = compute_events_diff(desired, live)[0]

    assert row.kind is ChangeKind.CONFLICT
    assert row.reason == "duplicate live events object key: event_routes:route.dup"


def test_events_validate_cli_is_schema_only(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _minimal_doc())

    result = CliRunner().invoke(main, ["validate", str(path), "--json"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["family"] == EVENTS_FAMILY
    assert payload["mode"] == "schema_only"


def test_events_plan_cli_exits_capability_error(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _minimal_doc())

    result = CliRunner().invoke(main, ["plan", str(path), "--json"], catch_exceptions=False)

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert "plan/apply is upstream-gap" in result.output
