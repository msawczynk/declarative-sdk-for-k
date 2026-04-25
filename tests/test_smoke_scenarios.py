"""Tests for the live-smoke scenario registry.

The live smoke itself needs a real Keeper tenant and can't run in CI.
These tests prove the offline half of every scenario — the manifest
fragment each scenario produces — passes schema + typed-model +
planner validation. If one of these fails, the live run for that
scenario can't possibly succeed and we'd rather catch it here than
burn a tenant round-trip.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_SMOKE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "smoke"
sys.path.insert(0, str(_SMOKE_DIR))

import scenarios as smoke_scenarios  # noqa: E402

from keeper_sdk.core.diff import compute_diff  # noqa: E402
from keeper_sdk.core.graph import build_graph, execution_order  # noqa: E402
from keeper_sdk.core.manifest import load_manifest  # noqa: E402
from keeper_sdk.core.normalize import to_pam_import_json  # noqa: E402
from keeper_sdk.core.planner import build_plan  # noqa: E402
from keeper_sdk.core.schema import validate_manifest  # noqa: E402

PAM_CONFIG_UID_REF = "lab-cfg"
TITLE_PREFIX = "sdk-smoke"


def _wrap_manifest(resources: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap scenario resources in the same envelope ``smoke.py`` uses."""
    return {
        "version": "1",
        "name": "sdk-smoke-testuser2",
        "shared_folders": {
            "resources": {
                "uid_ref": "smoke-sf-resources",
                "manage_users": True,
                "manage_records": True,
                "can_edit": True,
                "can_share": True,
            }
        },
        "gateways": [{"uid_ref": "lab-gw", "name": "Lab GW Rocky", "mode": "reference_existing"}],
        "pam_configurations": [
            {
                "uid_ref": PAM_CONFIG_UID_REF,
                "environment": "local",
                "title": "Lab Rocky PAM Configuration",
                "gateway_uid_ref": "lab-gw",
            }
        ],
        "resources": resources,
    }


def test_registry_lists_expected_scenarios() -> None:
    names = smoke_scenarios.names()
    assert "pamMachine" in names
    assert "pamDatabase" in names
    assert "pamDirectory" in names
    assert "pamRemoteBrowser" in names
    assert "pamUserNested" in names


def test_unknown_scenario_raises() -> None:
    with pytest.raises(KeyError, match="unknown smoke scenario"):
        smoke_scenarios.get("pamImaginary")


def test_pammachine_scenario_matches_legacy_titles() -> None:
    """Pin backwards compatibility: the legacy smoke expected exactly
    ``sdk-smoke-host-1`` and ``sdk-smoke-host-2`` as the two managed
    record titles. Anything else would regress the existing
    one-command invocation."""
    spec = smoke_scenarios.get("pamMachine")
    resources = spec.build_resources(PAM_CONFIG_UID_REF, TITLE_PREFIX)
    titles = [r["title"] for r in resources]
    assert titles == ["sdk-smoke-host-1", "sdk-smoke-host-2"]
    for resource in resources:
        assert resource["type"] == "pamMachine"
        assert resource["pam_configuration_uid_ref"] == PAM_CONFIG_UID_REF


@pytest.mark.parametrize("spec", smoke_scenarios.all_scenarios(), ids=lambda s: s.name)
def test_scenario_manifest_is_schema_valid_and_plans_cleanly(
    spec: smoke_scenarios.ScenarioSpec, tmp_path: Path
) -> None:
    """Every scenario must produce a manifest that clears schema,
    typed loading, graph + planner stages without a live tenant.
    This is the 'offline smoke' gate — catches drift between the
    scenario payload and the schema before anyone burns a tenant run.
    """
    resources = spec.build_resources(PAM_CONFIG_UID_REF, TITLE_PREFIX)
    assert resources, f"scenario {spec.name} produced no resources"
    for resource in resources:
        assert resource.get("uid_ref"), "every resource needs a uid_ref"
        assert resource.get("title"), "every resource needs a title"
        assert resource.get("type") == spec.resource_type
        assert resource.get("pam_configuration_uid_ref") == PAM_CONFIG_UID_REF

    document = _wrap_manifest(resources)
    validate_manifest(document)

    import yaml

    path = tmp_path / f"{spec.name}.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    manifest = load_manifest(path)
    order = execution_order(build_graph(manifest))
    changes = compute_diff(manifest, [], allow_delete=True)
    plan = build_plan(manifest.name, changes, order)
    expected_records = spec.expected_records(PAM_CONFIG_UID_REF, TITLE_PREFIX)
    plan_records = [(change.resource_type, change.title) for change in plan.creates]
    for expected in expected_records:
        assert expected in plan_records, f"scenario {spec.name}: missing create {expected}"


def test_pamuser_nested_scenario_exercises_full_offline_path(tmp_path: Path) -> None:
    """Pin pamUser as nested under resources[].users[], not top-level resources[]."""
    spec = smoke_scenarios.get("pamUserNested")
    resources = spec.build_resources(PAM_CONFIG_UID_REF, TITLE_PREFIX)
    document = _wrap_manifest(resources)
    validate_manifest(document)

    import yaml

    path = tmp_path / "pamUserNested.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    manifest = load_manifest(path)
    assert manifest.resources[0].users[0].type == "pamUser"
    assert manifest.iter_all_users()[0].title == "sdk-smoke-pam-user-1"

    order = execution_order(build_graph(manifest))
    changes = compute_diff(manifest, [], allow_delete=True)
    plan = build_plan(manifest.name, changes, order)
    plan_records = {(change.resource_type, change.title) for change in plan.creates}
    assert ("pamMachine", "sdk-smoke-host-with-user") in plan_records
    assert ("pamUser", "sdk-smoke-pam-user-1") in plan_records

    converted = to_pam_import_json(manifest.model_dump(mode="python", exclude_none=True))
    converted_resource = converted["pam_data"]["resources"][0]
    converted_user = converted_resource["users"][0]
    assert "uid_ref" not in converted_user
    assert converted_user["type"] == "pamUser"
    assert converted_user["title"] == "sdk-smoke-pam-user-1"
    assert converted_user["login"] == "sdk-smoke-user"


def test_noop_verifier_accepts_empty_records() -> None:
    """Default verifier is a no-op; it must accept any shape."""
    spec = smoke_scenarios.get("pamMachine")
    spec.verify([])
    spec.verify([object()])


def test_database_verifier_rejects_missing_database_type() -> None:
    spec = smoke_scenarios.get("pamDatabase")

    class _Record:
        resource_type = "pamDatabase"
        title = "smoke-db"
        payload: dict[str, Any] = {}

    with pytest.raises(AssertionError, match="database_type"):
        spec.verify([_Record()])


def test_directory_verifier_rejects_missing_directory_type() -> None:
    spec = smoke_scenarios.get("pamDirectory")

    class _Record:
        resource_type = "pamDirectory"
        title = "smoke-dir"
        payload: dict[str, Any] = {}

    with pytest.raises(AssertionError, match="directory_type"):
        spec.verify([_Record()])


def test_remote_browser_verifier_rejects_missing_isolation_flag() -> None:
    spec = smoke_scenarios.get("pamRemoteBrowser")

    class _Record:
        resource_type = "pamRemoteBrowser"
        title = "smoke-rbi"
        payload: dict[str, Any] = {"pam_settings": {"options": {}}}

    with pytest.raises(AssertionError, match="remote_browser_isolation"):
        spec.verify([_Record()])


def test_pamuser_nested_verifier_rejects_missing_login() -> None:
    spec = smoke_scenarios.get("pamUserNested")

    class _Record:
        resource_type = "pamUser"
        title = "smoke-user"
        payload: dict[str, Any] = {}

    with pytest.raises(AssertionError, match="login"):
        spec.verify([_Record()])
