"""keeper-epm.v1 offline schema, model, diff, and CLI tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.epm_diff import compute_epm_diff
from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.manifest import load_declarative_manifest_string
from keeper_sdk.core.models_epm import EPM_FAMILY, EpmManifestV1, load_epm_manifest
from keeper_sdk.core.schema import load_schema_for_family, validate_manifest


def _minimal_doc() -> dict[str, Any]:
    return {"schema": EPM_FAMILY}


def _full_doc() -> dict[str, Any]:
    return {
        "schema": EPM_FAMILY,
        "watchlists": [
            {
                "uid_ref": "wl.trusted.admin-tools",
                "name": "Trusted admin tools",
                "description": "augenblik.eu MSP managed-company EPM lab allowlist",
                "policy_type": "allowlist",
                "entries": ["/usr/bin/sudo", "C:\\Program Files\\Keeper\\*.exe"],
            },
            {
                "uid_ref": "wl.blocked.legacy",
                "name": "Blocked legacy tools",
                "description": "Known unsupported privilege helpers",
                "policy_type": "blocklist",
                "entries": ["psexec.exe", "legacy-elevate"],
            },
        ],
        "policies": [
            {
                "uid_ref": "pol.augenblik.approval",
                "name": "augenblik.eu approval",
                "elevation_type": "approval",
                "target_users": ["testuser1@augenblik.eu", "testuser2@augenblik.eu"],
                "target_groups": ["augenblik-eu-admins"],
                "application_patterns": ["keeper://epm/apps/admin-tools/*"],
            },
            {
                "uid_ref": "pol.augenblik.denied",
                "name": "augenblik.eu deny legacy",
                "elevation_type": "denied",
                "target_users": ["contractor@augenblik.eu"],
                "target_groups": [],
                "application_patterns": ["*psexec*", "*legacy-elevate*"],
            },
        ],
        "approvers": [
            {
                "uid_ref": "apr.augenblik.ops",
                "name": "Aungenblik Ops",
                "email": "ops@augenblik.eu",
                "scope_uid_refs": ["pol.augenblik.approval"],
            }
        ],
        "audit_config": {
            "retention_days": 365,
            "alert_on_denied": True,
            "export_format": "siem",
        },
    }


def _manifest(document: dict[str, Any] | None = None) -> EpmManifestV1:
    return load_epm_manifest(document or _full_doc())


def _write_manifest(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "epm.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_epm_schema_is_packaged_under_canonical_path() -> None:
    schema = load_schema_for_family(EPM_FAMILY)

    assert schema["title"] == EPM_FAMILY
    assert "watchlists" in schema["properties"]
    assert schema["x-keeper-live-proof"]["status"] == "upstream-gap"


def test_epm_validate_minimal_manifest() -> None:
    assert validate_manifest(_minimal_doc()) == EPM_FAMILY


def test_epm_validate_full_manifest() -> None:
    assert validate_manifest(_full_doc()) == EPM_FAMILY


def test_epm_invalid_watchlist_policy_type() -> None:
    document = _full_doc()
    document["watchlists"][0]["policy_type"] = "monitor"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "not one of" in exc.value.reason


def test_epm_invalid_policy_elevation_type() -> None:
    document = _full_doc()
    document["policies"][0]["elevation_type"] = "prompt"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "not one of" in exc.value.reason


def test_epm_invalid_audit_export_format() -> None:
    document = _full_doc()
    document["audit_config"]["export_format"] = "xml"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "not one of" in exc.value.reason


def test_epm_invalid_missing_policy_required_field() -> None:
    document = _full_doc()
    del document["policies"][0]["target_users"]

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert exc.value.context["location"] == "policies/0"
    assert "target_users" in exc.value.reason


def test_epm_invalid_email_rejected() -> None:
    document = _full_doc()
    document["approvers"][0]["email"] = "not-an-email"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert exc.value.context["location"] == "approvers/0/email"


def test_epm_rejects_unknown_property() -> None:
    document = _full_doc()
    document["watchlists"][0]["unexpected"] = True

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "Additional properties" in exc.value.reason


def test_epm_loader_returns_typed_model() -> None:
    loaded = load_declarative_manifest_string(json.dumps(_full_doc()), suffix=".json")

    assert isinstance(loaded, EpmManifestV1)
    assert loaded.policies[0].target_users == [
        "testuser1@augenblik.eu",
        "testuser2@augenblik.eu",
    ]


def test_epm_manifest_roundtrip() -> None:
    manifest = _manifest()
    dumped = manifest.model_dump(mode="json", exclude_none=True, by_alias=True)
    loaded = load_declarative_manifest_string(json.dumps(dumped), suffix=".json")

    assert isinstance(loaded, EpmManifestV1)
    assert loaded.model_dump(mode="json", exclude_none=True, by_alias=True) == dumped


def test_epm_loader_rejects_duplicate_uid_refs() -> None:
    document = _full_doc()
    document["approvers"][0]["uid_ref"] = "pol.augenblik.approval"

    with pytest.raises(SchemaError) as exc:
        load_epm_manifest(document)

    assert "duplicate uid_ref" in exc.value.reason


def test_epm_loader_rejects_unknown_approver_scope() -> None:
    document = _full_doc()
    document["approvers"][0]["scope_uid_refs"] = ["pol.missing"]

    with pytest.raises(SchemaError) as exc:
        load_epm_manifest(document)

    assert "scope_uid_refs" in exc.value.reason


def test_epm_diff_detects_policy_change() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["policies"][0]["elevation_type"] = "auto"

    row = next(
        change
        for change in compute_epm_diff(desired, live)
        if change.uid_ref == "pol.augenblik.approval"
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.before == {"elevation_type": "auto"}
    assert row.after == {"elevation_type": "approval"}


def test_epm_diff_detects_watchlist_entries_change_order_insensitive() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["watchlists"][0]["entries"] = [
        "C:\\Program Files\\Keeper\\*.exe",
        "/usr/bin/sudo",
    ]

    rows = compute_epm_diff(desired, live)

    assert {change.kind for change in rows} == {ChangeKind.NOOP}


def test_epm_diff_detects_audit_config_change() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["audit_config"]["retention_days"] = 90

    row = next(
        change for change in compute_epm_diff(desired, live) if change.uid_ref == "audit_config"
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.before == {"retention_days": 90}
    assert row.after == {"retention_days": 365}


def test_epm_validate_cli_is_schema_only(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _full_doc())

    result = CliRunner().invoke(main, ["validate", str(path), "--json"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["family"] == EPM_FAMILY
    assert payload["mode"] == "schema_only"


def test_epm_plan_cli_exits_upstream_gap(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _full_doc())

    result = CliRunner().invoke(main, ["plan", str(path), "--json"], catch_exceptions=False)

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert EPM_FAMILY in result.output
    assert "upstream-gap" in result.output


def test_epm_apply_cli_exits_upstream_gap(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _full_doc())

    result = CliRunner().invoke(main, ["apply", str(path), "--dry-run"], catch_exceptions=False)

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert EPM_FAMILY in result.output
    assert "upstream-gap" in result.output
