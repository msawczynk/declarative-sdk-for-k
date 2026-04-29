"""keeper-pam-extended.v1 offline schema, model, diff, and CLI tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY
from keeper_sdk.core import (
    PAM_EXTENDED_FAMILY,
    PamExtendedManifestV1,
    load_schema_for_family,
)
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.manifest import load_declarative_manifest_string
from keeper_sdk.core.models_pam_extended import load_pam_extended_manifest
from keeper_sdk.core.pam_extended_diff import compute_pam_extended_diff
from keeper_sdk.core.schema import validate_manifest


def _minimal_doc() -> dict[str, Any]:
    return {
        "schema": PAM_EXTENDED_FAMILY,
        "gateway_configs": [
            {
                "gateway_uid_ref": "gw.edge",
                "network_segment": "corp-edge",
                "allowed_ports": [22, 3389],
                "health_check_interval_s": 30,
            }
        ],
    }


def _full_doc() -> dict[str, Any]:
    return {
        "schema": PAM_EXTENDED_FAMILY,
        "gateway_configs": [
            {
                "gateway_uid_ref": "gw.edge",
                "network_segment": "corp-edge",
                "allowed_ports": [22, 3389, 3306],
                "health_check_interval_s": 30,
            }
        ],
        "rotation_schedules": [
            {
                "name": "DB hourly",
                "uid_ref": "rot.db_hourly",
                "cron_expr": "0 * * * *",
                "resource_uid_refs": ["res.db_prod", "res.db_readonly"],
                "notify_emails": ["ops@example.com"],
            }
        ],
        "discovery_rules": [
            {
                "name": "SSH scan",
                "uid_ref": "disc.ssh",
                "scan_network": True,
                "target_cidr": "10.20.0.0/16",
                "protocol": "ssh",
                "credential_uid_ref": "cred.discovery",
            }
        ],
        "service_mappings": [
            {
                "name": "nginx",
                "uid_ref": "svc.nginx",
                "service_type": "unix_daemon",
                "host_uid_ref": "host.web01",
                "credential_uid_ref": "cred.nginx",
            }
        ],
    }


def _manifest(document: dict[str, Any] | None = None) -> PamExtendedManifestV1:
    return load_pam_extended_manifest(document or _full_doc())


def _write_manifest(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "pam-extended.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_pam_extended_schema_is_packaged_under_canonical_path() -> None:
    schema = load_schema_for_family(PAM_EXTENDED_FAMILY)

    assert schema["title"] == PAM_EXTENDED_FAMILY
    assert "service_mappings" in schema["properties"]


def test_pam_extended_validate_empty_manifest() -> None:
    assert validate_manifest({"schema": PAM_EXTENDED_FAMILY}) == PAM_EXTENDED_FAMILY


def test_pam_extended_validate_minimal_gateway_config() -> None:
    assert validate_manifest(_minimal_doc()) == PAM_EXTENDED_FAMILY


def test_pam_extended_validate_full_manifest() -> None:
    assert validate_manifest(_full_doc()) == PAM_EXTENDED_FAMILY


def test_pam_extended_invalid_missing_gateway_required_field() -> None:
    document = _minimal_doc()
    del document["gateway_configs"][0]["network_segment"]

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert exc.value.context["location"] == "gateway_configs/0"
    assert "network_segment" in exc.value.reason


def test_pam_extended_invalid_port_range() -> None:
    document = _minimal_doc()
    document["gateway_configs"][0]["allowed_ports"] = [70000]

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "maximum" in exc.value.reason


def test_pam_extended_invalid_discovery_protocol() -> None:
    document = _full_doc()
    document["discovery_rules"][0]["protocol"] = "telnet"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "not one of" in exc.value.reason


def test_pam_extended_invalid_service_type() -> None:
    document = _full_doc()
    document["service_mappings"][0]["service_type"] = "launchd"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "not one of" in exc.value.reason


def test_pam_extended_rejects_unknown_property() -> None:
    document = _minimal_doc()
    document["gateway_configs"][0]["unexpected"] = True

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "Additional properties" in exc.value.reason


def test_pam_extended_loader_returns_typed_model() -> None:
    loaded = load_declarative_manifest_string(json.dumps(_minimal_doc()), suffix=".json")

    assert isinstance(loaded, PamExtendedManifestV1)
    assert loaded.gateway_configs[0].allowed_ports == [22, 3389]


def test_pam_extended_manifest_roundtrip() -> None:
    manifest = _manifest()
    dumped = manifest.model_dump(mode="json", exclude_none=True, by_alias=True)
    loaded = load_declarative_manifest_string(json.dumps(dumped), suffix=".json")

    assert isinstance(loaded, PamExtendedManifestV1)
    assert loaded.model_dump(mode="json", exclude_none=True, by_alias=True) == dumped


def test_pam_extended_loader_rejects_duplicate_uid_refs() -> None:
    document = _full_doc()
    document["service_mappings"][0]["uid_ref"] = "rot.db_hourly"

    with pytest.raises(SchemaError) as exc:
        load_pam_extended_manifest(document)

    assert "duplicate uid_ref" in exc.value.reason


def test_pam_extended_loader_rejects_duplicate_gateway_refs() -> None:
    document = _full_doc()
    document["gateway_configs"].append(
        {
            "gateway_uid_ref": "gw.edge",
            "network_segment": "corp-alt",
            "allowed_ports": [443],
            "health_check_interval_s": 60,
        }
    )

    with pytest.raises(SchemaError) as exc:
        load_pam_extended_manifest(document)

    assert "duplicate gateway_uid_ref" in exc.value.reason


def test_pam_extended_diff_detects_schedule_change() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["rotation_schedules"][0]["cron_expr"] = "30 * * * *"

    row = next(
        change
        for change in compute_pam_extended_diff(desired, live)
        if change.uid_ref == "rot.db_hourly"
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.before == {"cron_expr": "30 * * * *"}
    assert row.after == {"cron_expr": "0 * * * *"}


def test_pam_extended_diff_detects_new_discovery_rule() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["discovery_rules"] = []

    row = next(
        change
        for change in compute_pam_extended_diff(desired, live)
        if change.resource_type == "pam_extended_discovery_rule"
    )

    assert row.kind is ChangeKind.CREATE
    assert row.uid_ref == "disc.ssh"


def test_pam_extended_diff_detects_gateway_network_segment_change() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["gateway_configs"][0]["network_segment"] = "corp-legacy"

    row = next(
        change
        for change in compute_pam_extended_diff(desired, live)
        if change.resource_type == "pam_extended_gateway_config"
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.before == {"network_segment": "corp-legacy"}
    assert row.after == {"network_segment": "corp-edge"}


def test_pam_extended_diff_noops_matching_snapshot() -> None:
    manifest = _manifest()
    live = manifest.model_dump(mode="python", exclude_none=True, by_alias=True)

    changes = compute_pam_extended_diff(manifest, live)

    assert {change.kind for change in changes} == {ChangeKind.NOOP}


def test_pam_extended_validate_cli_is_schema_only(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _minimal_doc())

    result = CliRunner().invoke(main, ["validate", str(path), "--json"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["family"] == PAM_EXTENDED_FAMILY
    assert payload["mode"] == "schema_only"


def test_pam_extended_plan_cli_exits_preview_capability(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _minimal_doc())

    result = CliRunner().invoke(main, ["plan", str(path), "--json"], catch_exceptions=False)

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert PAM_EXTENDED_FAMILY in result.output
    assert "preview-gated" in result.output
