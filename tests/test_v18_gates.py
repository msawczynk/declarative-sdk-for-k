"""Offline coverage for Commander v18 feature gates."""

from __future__ import annotations

import pytest

from keeper_sdk.core import build_graph, compute_diff, execution_order
from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.models import Manifest
from keeper_sdk.core.planner import Plan, build_plan
from keeper_sdk.providers import commander_cli, commander_version
from keeper_sdk.providers.commander_cli import CommanderCliProvider
from keeper_sdk.providers.mock import MockProvider


def _rotation_manifest():
    return Manifest.model_validate(
        {
            "version": "1",
            "name": "v18-gates",
            "shared_folders": {
                "resources": {
                    "uid_ref": "sf.resources",
                    "manage_users": True,
                    "manage_records": True,
                    "can_edit": True,
                    "can_share": True,
                }
            },
            "gateways": [
                {"uid_ref": "gw.lab", "name": "Lab Gateway", "mode": "reference_existing"}
            ],
            "pam_configurations": [
                {
                    "uid_ref": "cfg.lab",
                    "environment": "local",
                    "title": "Lab Config",
                    "gateway_uid_ref": "gw.lab",
                    "options": {"connections": "on", "rotation": "on"},
                    "network_id": "lab-net",
                    "network_cidr": "10.0.0.0/24",
                }
            ],
            "resources": [
                {
                    "uid_ref": "res.host",
                    "type": "pamMachine",
                    "title": "host",
                    "pam_configuration_uid_ref": "cfg.lab",
                    "shared_folder": "resources",
                    "host": "10.0.0.10",
                    "port": "22",
                    "users": [
                        {
                            "uid_ref": "user.root",
                            "type": "pamUser",
                            "title": "root",
                            "rotation_scripts": [
                                {"script_uid": "SCRIPT_UID", "script_name": "rotate-root"}
                            ],
                        }
                    ],
                }
            ],
        }
    )


def _rotation_plan_output(monkeypatch: pytest.MonkeyPatch, *, v18: bool) -> str:
    monkeypatch.setattr(commander_version, "v18_rotation_info_json", lambda: v18)
    manifest = _rotation_manifest()
    provider = MockProvider(manifest.name)
    changes = compute_diff(manifest, provider.discover())
    plan = build_plan(manifest.name, changes, execution_order(build_graph(manifest)))
    return "\n".join(change.reason or "" for change in plan.changes)


def test_rotation_scripts_no_warning_v18(monkeypatch: pytest.MonkeyPatch) -> None:
    output = _rotation_plan_output(monkeypatch, v18=True)

    assert "rotation_scripts readback" not in output


def test_rotation_scripts_warning_v17(monkeypatch: pytest.MonkeyPatch) -> None:
    output = _rotation_plan_output(monkeypatch, v18=False)

    assert "rotation_scripts readback" in output


@pytest.mark.skip(reason="wire in P2")
def test_project_export_native_path_v18(monkeypatch: pytest.MonkeyPatch) -> None:
    # TODO(P2): route the live export CLI through CommanderCliProvider.export_pam_project_json,
    # mock native `pam project export --project-uid <uid> --format json`, and assert no ls/get
    # synthesis occurs when DSK_COMMANDER_V18=1.
    monkeypatch.setenv("DSK_COMMANDER_V18", "1")


def _token_change() -> Change:
    return Change(
        kind=ChangeKind.CREATE,
        uid_ref="token.bootstrap",
        resource_type="ksm_token",
        title="bootstrap",
        after={
            "uid_ref": "token.bootstrap",
            "name": "bootstrap",
            "app_uid_ref": "keeper-ksm:apps:APP_UID",
            "one_time": True,
        },
    )


def test_sm_token_add_v17_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = CommanderCliProvider.__new__(CommanderCliProvider)
    monkeypatch.setattr(commander_cli, "_ensure_keepercommander_version_for_apply", lambda: None)
    monkeypatch.setattr(commander_cli, "_v18_sm_token_add", lambda: False)

    with pytest.raises(CapabilityError, match="secrets-manager token add"):
        provider.apply_ksm_plan(Plan("ksm", [_token_change()], ["token.bootstrap"]))


def test_sm_token_add_v18_calls_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = CommanderCliProvider.__new__(CommanderCliProvider)
    calls: list[list[str]] = []

    def fake_run_cmd(args: list[str]) -> str:
        calls.append(args)
        return "ONE_TIME_TOKEN_VALUE\n"

    monkeypatch.setenv("DSK_COMMANDER_V18", "1")
    monkeypatch.setattr(commander_cli, "_ensure_keepercommander_version_for_apply", lambda: None)
    provider._run_cmd = fake_run_cmd

    outcomes = provider.apply_ksm_plan(Plan("ksm", [_token_change()], ["token.bootstrap"]))

    assert calls == [["secrets-manager", "token", "add", "APP_UID"]]
    assert outcomes[0].details["token_created"] is True
    assert outcomes[0].keeper_uid == ""
