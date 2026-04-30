"""Focused keeper-epm.v1 offline manifest tests."""

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
from keeper_sdk.core.planner import build_plan


def _minimal_doc() -> dict[str, Any]:
    return {"schema": EPM_FAMILY, "policies": []}


def _policy(uid_ref: str, name: str, elevation_type: str = "approval") -> dict[str, Any]:
    return {
        "uid_ref": uid_ref,
        "name": name,
        "elevation_type": elevation_type,
        "target_users": ["alice@example.com"],
        "target_groups": ["admin-workstations"],
        "application_patterns": ["keeper://epm/apps/admin-tools/*"],
    }


def _policy_doc(*policies: dict[str, Any]) -> dict[str, Any]:
    return {"schema": EPM_FAMILY, "policies": list(policies)}


def _write_json(tmp_path: Path, name: str, document: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _epm_apply_order(manifest: EpmManifestV1) -> list[str]:
    return [uid_ref for uid_ref, _kind in manifest.iter_uid_refs()]


def test_epm_valid_minimal_manifest_with_empty_policies() -> None:
    manifest = load_epm_manifest(_minimal_doc())

    assert manifest.epm_schema == EPM_FAMILY
    assert manifest.policies == []
    assert manifest.watchlists == []
    assert manifest.approvers == []


def test_epm_missing_schema_field_raises_schema_error() -> None:
    with pytest.raises(SchemaError) as exc:
        load_epm_manifest({"policies": []})

    assert "schema" in exc.value.reason


def test_epm_roundtrip_after_order_build_remains_equal() -> None:
    manifest = load_epm_manifest(_policy_doc(_policy("pol.admin", "Admin elevation")))
    assert _epm_apply_order(manifest) == ["pol.admin"]

    dumped = manifest.model_dump(mode="json", exclude_none=True, by_alias=True)
    reloaded = load_declarative_manifest_string(json.dumps(dumped), suffix=".json")

    assert isinstance(reloaded, EpmManifestV1)
    assert reloaded.model_dump(mode="json", exclude_none=True, by_alias=True) == dumped


def test_epm_policy_entry_validation() -> None:
    document = _policy_doc(_policy("pol.admin", "Admin elevation", elevation_type="auto"))
    manifest = load_epm_manifest(document)

    assert manifest.policies[0].name == "Admin elevation"
    assert manifest.policies[0].elevation_type == "auto"
    assert manifest.policies[0].target_users == ["alice@example.com"]
    assert manifest.policies[0].target_groups == ["admin-workstations"]
    assert manifest.policies[0].application_patterns == ["keeper://epm/apps/admin-tools/*"]

    invalid = _policy_doc(_policy("pol.bad", "Bad policy", elevation_type="prompt"))
    with pytest.raises(SchemaError) as exc:
        load_epm_manifest(invalid)

    assert "not one of" in exc.value.reason


def test_epm_two_policy_manifest_plans_both_in_manifest_order() -> None:
    manifest = load_epm_manifest(
        _policy_doc(
            _policy("pol.zeta", "Zeta elevation"),
            _policy("pol.alpha", "Alpha elevation"),
        )
    )

    changes = compute_epm_diff(manifest, {}, manifest_name="epm-test")
    plan = build_plan("epm-test", changes, _epm_apply_order(manifest))

    assert [change.kind for change in plan.ordered()] == [ChangeKind.CREATE, ChangeKind.CREATE]
    assert [change.uid_ref for change in plan.ordered()] == ["pol.zeta", "pol.alpha"]


def test_epm_apply_mock_provider_exits_capability(tmp_path: Path) -> None:
    path = _write_json(tmp_path, "epm.json", _policy_doc(_policy("pol.admin", "Admin elevation")))

    result = CliRunner().invoke(
        main,
        ["--provider", "mock", "apply", "--auto-approve", str(path)],
        catch_exceptions=False,
    )

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert EPM_FAMILY in result.output


def test_epm_apply_mock_provider_reports_upstream_gap_or_pedm(tmp_path: Path) -> None:
    path = _write_json(tmp_path, "epm.json", _policy_doc(_policy("pol.admin", "Admin elevation")))

    result = CliRunner().invoke(
        main,
        ["--provider", "mock", "apply", "--auto-approve", str(path)],
        catch_exceptions=False,
    )

    assert "upstream-gap" in result.output or "PEDM" in result.output
    assert "PEDM tenant write/readback proof" in result.output


def test_epm_unknown_field_raises_schema_error() -> None:
    document = _minimal_doc()
    document["unexpected"] = True

    with pytest.raises(SchemaError) as exc:
        load_epm_manifest(document)

    assert "Additional properties" in exc.value.reason
