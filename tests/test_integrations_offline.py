"""Offline validate and plan-row coverage for integration manifest families."""

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
from keeper_sdk.core.integrations_identity_diff import compute_identity_diff
from keeper_sdk.core.models_integrations_events import (
    EVENTS_FAMILY,
    EventsManifestV1,
    load_events_manifest,
)
from keeper_sdk.core.models_integrations_identity import (
    IDENTITY_FAMILY,
    IdentityManifestV1,
    load_identity_manifest,
)
from keeper_sdk.core.planner import Plan, build_plan
from keeper_sdk.core.schema import load_schema_for_family, validate_manifest


def _identity_doc() -> dict[str, Any]:
    return {
        "schema": IDENTITY_FAMILY,
        "domains": [{"name": "acme.example.com"}],
    }


def _events_minimal_doc() -> dict[str, Any]:
    return {
        "schema": EVENTS_FAMILY,
        "name": "acme-events",
    }


def _events_row_doc() -> dict[str, Any]:
    document = _events_minimal_doc()
    document["automator_rules"] = [
        {
            "uid_ref": "rule.login",
            "name": "Login webhook",
            "trigger": "login",
            "action": "webhook",
            "endpoint_uid_ref": "endpoint.webhook",
        }
    ]
    return document


def _write_json(tmp_path: Path, name: str, document: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _identity_plan(manifest: IdentityManifestV1) -> Plan:
    changes = compute_identity_diff(manifest, {}, manifest_name=IDENTITY_FAMILY)
    return build_plan(IDENTITY_FAMILY, changes, [change.uid_ref or "" for change in changes])


def _events_plan(manifest: EventsManifestV1) -> Plan:
    changes = compute_events_diff(manifest, {}, manifest_name=manifest.name)
    return build_plan(
        manifest.name, changes, [uid_ref for uid_ref, _kind in manifest.iter_uid_refs()]
    )


def test_identity_minimal_manifest_validates_exit_zero(tmp_path: Path) -> None:
    schema = load_schema_for_family(IDENTITY_FAMILY)
    path = _write_json(tmp_path, "identity.json", _identity_doc())

    result = CliRunner().invoke(main, ["validate", str(path), "--json"], catch_exceptions=False)

    assert schema["title"] == IDENTITY_FAMILY
    assert "domains" in schema["properties"]
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["family"] == IDENTITY_FAMILY


def test_identity_diff_plan_rows_present() -> None:
    plan = _identity_plan(load_identity_manifest(_identity_doc()))

    assert len(plan.creates) == 1
    row = plan.creates[0]
    assert row.kind is ChangeKind.CREATE
    assert row.resource_type == "identity_domain"
    assert row.uid_ref == "acme.example.com"
    assert row.after["verified"] is False


def test_identity_unknown_field_raises_schema_error() -> None:
    document = _identity_doc()
    document["unexpected"] = True

    with pytest.raises(SchemaError):
        validate_manifest(document)


def test_identity_apply_mock_provider_exits_capability(tmp_path: Path) -> None:
    path = _write_json(tmp_path, "identity.json", _identity_doc())

    result = CliRunner().invoke(
        main,
        ["--provider", "mock", "apply", "--auto-approve", str(path)],
        catch_exceptions=False,
    )

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert IDENTITY_FAMILY in result.output


def test_identity_apply_mock_provider_reports_upstream_gap_reason(tmp_path: Path) -> None:
    path = _write_json(tmp_path, "identity.json", _identity_doc())

    result = CliRunner().invoke(
        main,
        ["--provider", "mock", "apply", "--auto-approve", str(path)],
        catch_exceptions=False,
    )

    assert "upstream-gap" in result.output
    assert "no Commander identity write verb confirmed" in result.output


def test_events_minimal_manifest_validates_exit_zero(tmp_path: Path) -> None:
    schema = load_schema_for_family(EVENTS_FAMILY)
    path = _write_json(tmp_path, "events.json", _events_minimal_doc())

    result = CliRunner().invoke(main, ["validate", str(path), "--json"], catch_exceptions=False)

    assert schema["title"] == EVENTS_FAMILY
    assert "automator_rules" in schema["properties"]
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["family"] == EVENTS_FAMILY


def test_events_diff_plan_rows_present() -> None:
    plan = _events_plan(load_events_manifest(_events_row_doc()))

    assert len(plan.creates) == 1
    row = plan.creates[0]
    assert row.kind is ChangeKind.CREATE
    assert row.resource_type == "events_automator_rule"
    assert row.uid_ref == "rule.login"
    assert row.after["endpoint_uid_ref"] == "endpoint.webhook"


def test_events_unknown_field_raises_schema_error() -> None:
    document = _events_minimal_doc()
    document["unexpected"] = True

    with pytest.raises(SchemaError):
        validate_manifest(document)


def test_events_apply_mock_provider_exits_capability(tmp_path: Path) -> None:
    path = _write_json(tmp_path, "events.json", _events_row_doc())

    result = CliRunner().invoke(
        main,
        ["--provider", "mock", "apply", "--auto-approve", str(path)],
        catch_exceptions=False,
    )

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert EVENTS_FAMILY in result.output


def test_events_apply_mock_provider_reports_upstream_gap_reason(tmp_path: Path) -> None:
    path = _write_json(tmp_path, "events.json", _events_row_doc())

    result = CliRunner().invoke(
        main,
        ["--provider", "mock", "apply", "--auto-approve", str(path)],
        catch_exceptions=False,
    )

    assert "upstream-gap" in result.output
    assert "no Commander events write verb confirmed" in result.output
