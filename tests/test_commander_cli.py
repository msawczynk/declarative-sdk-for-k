"""Tests for the Commander CLI provider discovery and apply flows."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import CapabilityError, CollisionError
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import MARKER_FIELD_LABEL, encode_marker, serialize_marker
from keeper_sdk.core.models import RotationScheduleOnDemand, RotationSettings
from keeper_sdk.core.planner import Plan
from keeper_sdk.providers.commander_cli import (
    CommanderCliProvider,
    _build_pam_rotation_edit_args,
    build_pam_rotation_edit_argvs,
    build_post_import_tuning_argvs,
)


def _provider(monkeypatch: pytest.MonkeyPatch, stdout: str = "") -> CommanderCliProvider:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", lambda self, args: stdout)
    return CommanderCliProvider(folder_uid="folder-uid")


def _discover_provider(
    monkeypatch: pytest.MonkeyPatch,
    *,
    ls_payload: object,
    get_payloads: dict[str, object] | None = None,
) -> CommanderCliProvider:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    def fake_run(self: CommanderCliProvider, args: list[str]) -> str:
        if args[:1] == ["ls"]:
            return json.dumps(ls_payload) if not isinstance(ls_payload, str) else ls_payload
        if args[:1] == ["get"]:
            uid = args[1]
            payload = (get_payloads or {}).get(uid)
            if payload is None:
                raise AssertionError(f"unexpected get uid {uid}")
            return json.dumps(payload) if not isinstance(payload, str) else payload
        raise AssertionError(f"unexpected args {args}")

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", fake_run)
    return CommanderCliProvider(folder_uid="folder-uid")


def _resolved_tree_entries(*, project_name: str = "customer-prod") -> dict[tuple[str, ...], object]:
    return {
        ("ls", "--format", "json", "PAM Environments"): [
            {"type": "folder", "uid": "project-folder", "name": project_name}
        ],
        ("ls", "--format", "json", "project-folder"): [
            {"type": "folder", "uid": "resources-folder", "name": f"{project_name} - Resources"}
        ],
    }


def _install_fake_write_marker(monkeypatch: pytest.MonkeyPatch, calls: list[list[str]]) -> None:
    """`_write_marker` no longer shells out to `record-update` — it uses the
    in-process Commander vault API. Tests pre-date this, so we fake the
    in-process helper by recording a synthetic argv in the same shape the
    old subprocess call would have produced."""
    from keeper_sdk.core.metadata import MARKER_FIELD_LABEL, serialize_marker

    def fake_write_marker(self, keeper_uid: str, marker: dict) -> None:
        payload = serialize_marker(marker)
        calls.append(
            [
                "record-update",
                "--record",
                keeper_uid,
                "-cf",
                f"{MARKER_FIELD_LABEL}={payload}",
            ]
        )

    monkeypatch.setattr(CommanderCliProvider, "_write_marker", fake_write_marker)


def test_run_cmd_retries_subprocess_once_on_session_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if len(calls) == 1:
            return subprocess.CompletedProcess(
                cmd,
                1,
                stdout="",
                stderr="session_token_expired: refresh needed",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="deleted", stderr="")

    monkeypatch.setattr("keeper_sdk.providers.commander_cli.subprocess.run", fake_run)

    provider = CommanderCliProvider(
        folder_uid="folder-uid",
        config_file="/tmp/config.json",
        keeper_password="secret",
    )

    assert provider._run_cmd(["rm", "--force", "UID"]) == "deleted"
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert calls[0][:4] == ["keeper", "--batch-mode", "--config", "/tmp/config.json"]


def test_run_cmd_does_not_retry_subprocess_non_session_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="permission denied")

    monkeypatch.setattr("keeper_sdk.providers.commander_cli.subprocess.run", fake_run)

    provider = CommanderCliProvider(folder_uid="folder-uid")

    with pytest.raises(CapabilityError, match="keeper rm --force UID failed"):
        provider._run_cmd(["rm", "--force", "UID"])

    assert len(calls) == 1


def test_run_cmd_routes_pam_gateway_list_in_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    seen: list[tuple[object, str]] = []

    def fake_get_params(self: CommanderCliProvider) -> object:
        self._keeper_params = object()
        self._keeper_login_attempted = True
        return self._keeper_params

    class _FakeGatewayList:
        def execute(self, params: object, **kwargs: object) -> str:
            seen.append((params, str(kwargs["format"])))
            return '{"gateways":[]}'

    monkeypatch.setattr(CommanderCliProvider, "_get_keeper_params", fake_get_params)
    import keepercommander.api as keeper_api

    monkeypatch.setattr(keeper_api, "sync_down", lambda _params: None)
    monkeypatch.setitem(
        sys.modules,
        "keepercommander.commands.discoveryrotation",
        types.SimpleNamespace(PAMGatewayListCommand=_FakeGatewayList),
    )

    provider = CommanderCliProvider(folder_uid="folder-uid")

    assert provider._run_cmd(["pam", "gateway", "list", "--format", "json"]) == '{"gateways":[]}'
    assert len(seen) == 1
    assert seen[0][1] == "json"


def test_run_cmd_refreshes_pam_config_list_in_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    params = [object(), object()]
    seen: list[object] = []

    def fake_get_params(self: CommanderCliProvider) -> object:
        param = params[len(seen)]
        self._keeper_params = param
        self._keeper_login_attempted = True
        return param

    class _FakeConfigList:
        def execute(self, params: object, **kwargs: object) -> str:
            seen.append(params)
            assert kwargs["format"] == "json"
            if len(seen) == 1:
                raise RuntimeError("session token expired")
            return '{"configurations":[]}'

    monkeypatch.setattr(CommanderCliProvider, "_get_keeper_params", fake_get_params)
    import keepercommander.api as keeper_api

    monkeypatch.setattr(keeper_api, "sync_down", lambda _params: None)
    monkeypatch.setitem(
        sys.modules,
        "keepercommander.commands.discoveryrotation",
        types.SimpleNamespace(PAMConfigurationListCommand=_FakeConfigList),
    )

    provider = CommanderCliProvider(folder_uid="folder-uid")

    assert (
        provider._run_cmd(["pam", "config", "list", "--format", "json"]) == '{"configurations":[]}'
    )
    assert seen == params


def test_run_cmd_routes_pam_rotation_edit_in_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    params = object()
    sync_calls: list[object] = []
    seen: list[tuple[object, dict[str, object]]] = []

    def fail_subprocess(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("rotation edit must not call subprocess")

    def fake_get_params(self: CommanderCliProvider) -> object:
        self._keeper_params = params
        self._keeper_login_attempted = True
        return params

    class _FakeRotationEdit:
        def get_parser(self) -> argparse.ArgumentParser:
            parser = argparse.ArgumentParser(prog="pam rotation edit")
            parser.add_argument("--record", dest="record_name", required=True)
            parser.add_argument("--config", dest="config")
            parser.add_argument("--resource", dest="resource")
            parser.add_argument("--admin-user", dest="admin")
            parser.add_argument("--rotation-profile", dest="rotation_profile")
            parser.add_argument("--schedulecron", dest="schedule_cron_data", action="append")
            parser.add_argument("--enable", dest="enable", action="store_true")
            parser.add_argument("--force", dest="force", action="store_true")
            return parser

        def execute(self, params: object, **kwargs: object) -> None:
            seen.append((params, kwargs))
            print("rotation ok")

    monkeypatch.setattr("keeper_sdk.providers.commander_cli.subprocess.run", fail_subprocess)
    monkeypatch.setattr(CommanderCliProvider, "_get_keeper_params", fake_get_params)
    import keepercommander.api as keeper_api

    monkeypatch.setattr(keeper_api, "sync_down", lambda call_params: sync_calls.append(call_params))
    monkeypatch.setitem(
        sys.modules,
        "keepercommander.commands.discoveryrotation",
        types.SimpleNamespace(PAMCreateRecordRotationCommand=_FakeRotationEdit),
    )

    provider = CommanderCliProvider(folder_uid="folder-uid")
    output = provider._run_cmd(
        [
            "pam",
            "rotation",
            "edit",
            "--record",
            "USER_UID",
            "--config",
            "CFG_UID",
            "--resource",
            "RES_UID",
            "--admin-user",
            "ADMIN_UID",
            "--rotation-profile",
            "general",
            "--schedulecron",
            "30 18 * * *",
            "--enable",
            "--force",
        ]
    )

    assert output.strip() == "rotation ok"
    assert sync_calls == [params]
    assert seen == [
        (
            params,
            {
                "record_name": "USER_UID",
                "config": "CFG_UID",
                "resource": "RES_UID",
                "admin": "ADMIN_UID",
                "rotation_profile": "general",
                "schedule_cron_data": ["30 18 * * *"],
                "enable": True,
                "force": True,
            },
        )
    ]


def test_run_cmd_wraps_in_process_pam_rotation_edit_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    def fail_subprocess(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("rotation edit must not call subprocess")

    class _FakeRotationEdit:
        def get_parser(self) -> argparse.ArgumentParser:
            parser = argparse.ArgumentParser(prog="pam rotation edit")
            parser.add_argument("--record", dest="record_name", required=True)
            parser.add_argument("--force", dest="force", action="store_true")
            return parser

        def execute(self, params: object, **kwargs: object) -> None:
            print("stdout before rotation failure")
            print("stderr before rotation failure", file=sys.stderr)
            raise RuntimeError("rotation failed")

    monkeypatch.setattr("keeper_sdk.providers.commander_cli.subprocess.run", fail_subprocess)
    monkeypatch.setitem(
        sys.modules,
        "keepercommander.commands.discoveryrotation",
        types.SimpleNamespace(PAMCreateRecordRotationCommand=_FakeRotationEdit),
    )
    import keepercommander.api as keeper_api

    monkeypatch.setattr(keeper_api, "sync_down", lambda _params: None)

    provider = CommanderCliProvider(folder_uid="folder-uid")
    provider._keeper_params = object()

    with pytest.raises(CapabilityError) as exc_info:
        provider._run_cmd(["pam", "rotation", "edit", "--record", "USER_UID", "--force"])

    assert "in-process keeper pam rotation edit failed" in exc_info.value.reason
    assert "RuntimeError: rotation failed" in exc_info.value.reason
    assert "stdout before rotation failure" in exc_info.value.context["stdout"]
    assert "stderr before rotation failure" in exc_info.value.context["stderr"]


def test_run_cmd_routes_ls_in_process_when_login_helper_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``ls <FOLDER> --format json`` runs in-process when login config detectable.

    Subprocess ``keeper`` against a dev workstation can hold a stale
    device_token and fail to resync just-applied records on a post-apply
    re-plan. Rerouting ``ls``/``get`` through the in-process Commander
    session shares the apply-time auth context so discover() always sees
    fresh state.
    """
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setenv("KEEPER_SDK_LOGIN_HELPER", "/dev/null")
    monkeypatch.delenv("KEEPER_EMAIL", raising=False)
    monkeypatch.delenv("KEEPER_PASSWORD", raising=False)
    monkeypatch.delenv("KEEPER_TOTP_SECRET", raising=False)

    params = object()
    sync_calls: list[object] = []
    seen: list[tuple[object, dict[str, object]]] = []

    def fail_subprocess(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("ls --format json must not call subprocess")

    def fake_get_params(self: CommanderCliProvider) -> object:
        self._keeper_params = params
        self._keeper_login_attempted = True
        return params

    class _FakeFolderList:
        def get_parser(self) -> argparse.ArgumentParser:
            parser = argparse.ArgumentParser(prog="ls")
            parser.add_argument("pattern", nargs="?")
            parser.add_argument("--format", dest="format")
            return parser

        def execute(self, params_arg: object, **kwargs: object) -> None:
            seen.append((params_arg, kwargs))
            print('[{"type": "record", "uid": "REC1", "title": "lab-linux-1"}]')

    monkeypatch.setattr("keeper_sdk.providers.commander_cli.subprocess.run", fail_subprocess)
    monkeypatch.setattr(CommanderCliProvider, "_get_keeper_params", fake_get_params)
    import keepercommander.api as keeper_api

    monkeypatch.setattr(keeper_api, "sync_down", lambda call_params: sync_calls.append(call_params))
    monkeypatch.setitem(
        sys.modules,
        "keepercommander.commands.folder",
        types.SimpleNamespace(FolderListCommand=_FakeFolderList),
    )

    provider = CommanderCliProvider(folder_uid="folder-uid")
    output = provider._run_cmd(["ls", "FOLDER_UID", "--format", "json"])

    assert '"REC1"' in output
    assert sync_calls == [params]
    assert seen == [(params, {"pattern": "FOLDER_UID", "format": "json"})]


def test_run_cmd_routes_get_in_process_when_login_helper_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirror of the ``ls`` route for ``get <UID> --format json``."""
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setenv("KEEPER_SDK_LOGIN_HELPER", "/dev/null")
    monkeypatch.delenv("KEEPER_EMAIL", raising=False)
    monkeypatch.delenv("KEEPER_PASSWORD", raising=False)
    monkeypatch.delenv("KEEPER_TOTP_SECRET", raising=False)

    params = object()
    sync_calls: list[object] = []
    seen: list[tuple[object, dict[str, object]]] = []

    def fail_subprocess(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("get --format json must not call subprocess")

    def fake_get_params(self: CommanderCliProvider) -> object:
        self._keeper_params = params
        self._keeper_login_attempted = True
        return params

    class _FakeRecordGet:
        def get_parser(self) -> argparse.ArgumentParser:
            parser = argparse.ArgumentParser(prog="get")
            parser.add_argument("uid")
            parser.add_argument("--format", dest="format")
            parser.add_argument("--unmask", dest="unmask", action="store_true")
            parser.add_argument("--legacy", dest="legacy", action="store_true")
            parser.add_argument("--include-dag", dest="include_dag", action="store_true")
            return parser

        def execute(self, params_arg: object, **kwargs: object) -> None:
            seen.append((params_arg, kwargs))
            print('{"record_uid":"REC1","title":"lab-linux-1","type":"pamMachine"}')

    monkeypatch.setattr("keeper_sdk.providers.commander_cli.subprocess.run", fail_subprocess)
    monkeypatch.setattr(CommanderCliProvider, "_get_keeper_params", fake_get_params)
    import keepercommander.api as keeper_api

    monkeypatch.setattr(keeper_api, "sync_down", lambda call_params: sync_calls.append(call_params))
    monkeypatch.setitem(
        sys.modules,
        "keepercommander.commands.record",
        types.SimpleNamespace(RecordGetUidCommand=_FakeRecordGet),
    )

    provider = CommanderCliProvider(folder_uid="folder-uid")
    output = provider._run_cmd(["get", "REC1", "--format", "json"])

    assert '"REC1"' in output
    assert sync_calls == [params]
    assert seen == [
        (
            params,
            {
                "uid": "REC1",
                "format": "json",
                "unmask": False,
                "legacy": False,
                "include_dag": False,
            },
        )
    ]


def test_run_cmd_falls_back_to_subprocess_for_ls_get_without_login_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No helper + no env creds + no cached params ⇒ ls/get use subprocess.

    Plain installs (no ``KEEPER_SDK_LOGIN_HELPER``, no env creds, no
    apply-time login yet) must keep working through subprocess so we don't
    regress users who only have ``~/.keeper/commander-config.json``.
    """
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.delenv("KEEPER_SDK_LOGIN_HELPER", raising=False)
    monkeypatch.delenv("KEEPER_EMAIL", raising=False)
    monkeypatch.delenv("KEEPER_PASSWORD", raising=False)
    monkeypatch.delenv("KEEPER_TOTP_SECRET", raising=False)

    seen_argv: list[list[str]] = []

    def fake_run(*args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        argv = list(args[0]) if args else []
        seen_argv.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr("keeper_sdk.providers.commander_cli.subprocess.run", fake_run)

    provider = CommanderCliProvider(folder_uid="folder-uid")
    assert provider._run_cmd(["ls", "FOLDER_UID", "--format", "json"]) == "[]"
    assert provider._run_cmd(["get", "REC1", "--format", "json"]) == "[]"
    assert any(argv[-4:] == ["ls", "FOLDER_UID", "--format", "json"] for argv in seen_argv)
    assert any(argv[-4:] == ["get", "REC1", "--format", "json"] for argv in seen_argv)


def test_can_attempt_in_process_login_truth_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_can_attempt_in_process_login`` honours the four signal sources."""
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    for var in ("KEEPER_SDK_LOGIN_HELPER", "KEEPER_EMAIL", "KEEPER_PASSWORD", "KEEPER_TOTP_SECRET"):
        monkeypatch.delenv(var, raising=False)

    provider = CommanderCliProvider(folder_uid="folder-uid")
    assert provider._can_attempt_in_process_login() is False

    monkeypatch.setenv("KEEPER_SDK_LOGIN_HELPER", "/dev/null")
    assert provider._can_attempt_in_process_login() is True
    monkeypatch.delenv("KEEPER_SDK_LOGIN_HELPER")

    for var, value in (
        ("KEEPER_EMAIL", "user@example.com"),
        ("KEEPER_PASSWORD", "secret"),
        ("KEEPER_TOTP_SECRET", "ABC123"),
    ):
        monkeypatch.setenv(var, value)
    assert provider._can_attempt_in_process_login() is True
    monkeypatch.delenv("KEEPER_TOTP_SECRET")
    assert provider._can_attempt_in_process_login() is False

    provider._keeper_params = object()
    assert provider._can_attempt_in_process_login() is True

    provider._keeper_params = None
    provider._keeper_login_attempted = True
    assert provider._can_attempt_in_process_login() is False


def test_build_pam_rotation_edit_args_for_cron_settings() -> None:
    args = _build_pam_rotation_edit_args(
        record_uid="user-uid",
        settings={
            "rotation": "general",
            "enabled": "on",
            "schedule": {"type": "CRON", "cron": "30 18 * * *"},
            "password_complexity": "32,5,5,5,5",
        },
        resource_uid="resource-uid",
        config_uid="config-uid",
        admin_uid="admin-uid",
    )

    assert args == [
        "pam",
        "rotation",
        "edit",
        "--record",
        "user-uid",
        "--config",
        "config-uid",
        "--resource",
        "resource-uid",
        "--admin-user",
        "admin-uid",
        "--rotation-profile",
        "general",
        "--schedulecron",
        "30 18 * * *",
        "--complexity",
        "32,5,5,5,5",
        "--enable",
        "--force",
    ]


def test_build_pam_rotation_edit_args_for_typed_on_demand_schedule() -> None:
    settings = RotationSettings(
        rotation="scripts_only",
        enabled="off",
        schedule=RotationScheduleOnDemand(type="on-demand"),
    )

    args = _build_pam_rotation_edit_args(
        record_uid="user-uid",
        settings=settings,
        config_uid="config-uid",
        schedule_only=True,
    )

    assert args == [
        "pam",
        "rotation",
        "edit",
        "--record",
        "user-uid",
        "--config",
        "config-uid",
        "--rotation-profile",
        "scripts_only",
        "--on-demand",
        "--disable",
        "--schedule-only",
        "--force",
    ]


def _rotation_manifest() -> dict:
    return {
        "version": "1",
        "name": "customer-prod",
        "pam_configurations": [
            {"uid_ref": "cfg.local", "title": "Lab Config", "environment": "local"}
        ],
        "resources": [
            {
                "uid_ref": "res.db",
                "type": "pamDatabase",
                "title": "db-prod",
                "pam_configuration_uid_ref": "cfg.local",
                "users": [
                    {
                        "uid_ref": "usr.db",
                        "type": "pamUser",
                        "title": "db-user",
                        "rotation_settings": {
                            "rotation": "general",
                            "enabled": "on",
                            "schedule": {"type": "CRON", "cron": "30 18 * * *"},
                            "password_complexity": "32,5,5,5,5",
                            "admin_uid_ref": "usr.admin",
                        },
                    },
                    {"uid_ref": "usr.admin", "type": "pamUser", "title": "admin-user"},
                ],
            }
        ],
    }


def _rotation_live_records() -> list[LiveRecord]:
    return [
        LiveRecord(
            keeper_uid="CFG_UID",
            title="Lab Config",
            resource_type="pam_configuration",
            marker={"uid_ref": "cfg.local"},
        ),
        LiveRecord(
            keeper_uid="RES_UID",
            title="db-prod",
            resource_type="pamDatabase",
            marker={"uid_ref": "res.db"},
        ),
        LiveRecord(
            keeper_uid="USER_UID",
            title="db-user",
            resource_type="pamUser",
            marker={"uid_ref": "usr.db"},
        ),
        LiveRecord(
            keeper_uid="ADMIN_UID",
            title="admin-user",
            resource_type="pamUser",
            marker={"uid_ref": "usr.admin"},
        ),
    ]


def test_build_pam_rotation_edit_argvs_for_nested_resource_user() -> None:
    argvs = build_pam_rotation_edit_argvs(
        _rotation_manifest(),
        live_records=_rotation_live_records(),
    )

    assert argvs == [
        [
            "pam",
            "rotation",
            "edit",
            "--record",
            "USER_UID",
            "--config",
            "CFG_UID",
            "--resource",
            "RES_UID",
            "--admin-user",
            "ADMIN_UID",
            "--rotation-profile",
            "general",
            "--schedulecron",
            "30 18 * * *",
            "--complexity",
            "32,5,5,5,5",
            "--enable",
            "--force",
        ]
    ]


def test_build_pam_rotation_edit_argvs_uses_plan_uids_when_live_omitted() -> None:
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.NOOP,
                uid_ref="cfg.local",
                resource_type="pam_configuration",
                title="Lab Config",
                keeper_uid="CFG_UID",
            ),
            Change(
                kind=ChangeKind.NOOP,
                uid_ref="res.db",
                resource_type="pamDatabase",
                title="db-prod",
                keeper_uid="RES_UID",
            ),
            Change(
                kind=ChangeKind.NOOP,
                uid_ref="usr.db",
                resource_type="pamUser",
                title="db-user",
                keeper_uid="USER_UID",
            ),
            Change(
                kind=ChangeKind.NOOP,
                uid_ref="usr.admin",
                resource_type="pamUser",
                title="admin-user",
                keeper_uid="ADMIN_UID",
            ),
        ],
        order=["cfg.local", "res.db", "usr.db", "usr.admin"],
    )

    argvs = build_pam_rotation_edit_argvs(_rotation_manifest(), plan=plan)

    assert argvs[0][argvs[0].index("--record") + 1] == "USER_UID"
    assert argvs[0][argvs[0].index("--resource") + 1] == "RES_UID"
    assert argvs[0][argvs[0].index("--config") + 1] == "CFG_UID"
    assert argvs[0][argvs[0].index("--admin-user") + 1] == "ADMIN_UID"


def test_build_pam_rotation_edit_argvs_uses_unique_title_parent_type_fallback() -> None:
    manifest = _rotation_manifest()
    manifest["resources"][0]["type"] = "pamMachine"
    live = [
        (
            LiveRecord(
                keeper_uid="RES_UID",
                title="db-prod",
                resource_type="pamDatabase",
            )
            if record.keeper_uid == "RES_UID"
            else record
        )
        for record in _rotation_live_records()
    ]

    argvs = build_pam_rotation_edit_argvs(manifest, live_records=live)

    assert argvs[0][argvs[0].index("--resource") + 1] == "RES_UID"


def test_build_pam_rotation_edit_argvs_rejects_duplicate_title_parent_fallback() -> None:
    manifest = _rotation_manifest()
    manifest["resources"][0]["type"] = "pamMachine"
    live = [
        (
            LiveRecord(
                keeper_uid="RES_UID",
                title="db-prod",
                resource_type="pamDatabase",
            )
            if record.keeper_uid == "RES_UID"
            else record
        )
        for record in _rotation_live_records()
    ]
    live.append(
        LiveRecord(
            keeper_uid="RES_UID_2",
            title="db-prod",
            resource_type="pamDirectory",
        )
    )

    with pytest.raises(ValueError, match="duplicate live parent resource match"):
        build_pam_rotation_edit_argvs(manifest, live_records=live)


def test_build_pam_rotation_edit_argvs_rejects_missing_parent_config_ref() -> None:
    manifest = _rotation_manifest()
    manifest["resources"][0].pop("pam_configuration_uid_ref")
    manifest["pam_configurations"].append(
        {"uid_ref": "cfg.other", "title": "Other Config", "environment": "local"}
    )

    with pytest.raises(ValueError, match="missing parent PAM configuration"):
        build_pam_rotation_edit_argvs(manifest, live_records=_rotation_live_records())


def test_build_pam_rotation_edit_argvs_requires_live_user() -> None:
    live = [record for record in _rotation_live_records() if record.keeper_uid != "USER_UID"]

    with pytest.raises(ValueError, match="missing live nested pamUser"):
        build_pam_rotation_edit_argvs(_rotation_manifest(), live_records=live)


def test_build_pam_rotation_edit_argvs_requires_live_resource() -> None:
    live = [record for record in _rotation_live_records() if record.keeper_uid != "RES_UID"]

    with pytest.raises(ValueError, match="missing live parent resource"):
        build_pam_rotation_edit_argvs(_rotation_manifest(), live_records=live)


def test_build_pam_rotation_edit_argvs_rejects_duplicate_live_match() -> None:
    live = _rotation_live_records() + [
        LiveRecord(
            keeper_uid="USER_UID_2",
            title="db-user-copy",
            resource_type="pamUser",
            marker={"uid_ref": "usr.db"},
        )
    ]

    with pytest.raises(ValueError, match="duplicate live nested pamUser match"):
        build_pam_rotation_edit_argvs(_rotation_manifest(), live_records=live)


def test_build_pam_rotation_edit_argvs_requires_config() -> None:
    live = [record for record in _rotation_live_records() if record.keeper_uid != "CFG_UID"]

    with pytest.raises(ValueError, match="missing live PAM configuration"):
        build_pam_rotation_edit_argvs(_rotation_manifest(), live_records=live)


def test_build_pam_rotation_edit_argvs_rejects_top_level_user_rotation() -> None:
    manifest = {
        "version": "1",
        "name": "customer-prod",
        "users": [
            {
                "uid_ref": "usr.top",
                "type": "pamUser",
                "title": "top-user",
                "rotation_settings": {"rotation": "general", "enabled": "on"},
            }
        ],
    }

    with pytest.raises(ValueError, match=r"top-level users\[\]\.rotation_settings is unsupported"):
        build_pam_rotation_edit_argvs(manifest, live_records=[])


def test_build_pam_rotation_edit_argvs_noops_without_rotation_settings() -> None:
    manifest = _rotation_manifest()
    for user in manifest["resources"][0]["users"]:
        user.pop("rotation_settings", None)

    assert build_pam_rotation_edit_argvs(manifest, live_records=[]) == []


def test_unsupported_default_rotation_schedule_has_precise_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider(monkeypatch)
    reasons = provider.unsupported_capabilities(
        {
            "version": "1",
            "name": "proj",
            "pam_configurations": [
                {
                    "uid_ref": "cfg",
                    "environment": "local",
                    "default_rotation_schedule": {"type": "CRON", "cron": "30 18 * * *"},
                }
            ],
        }
    )

    assert len(reasons) == 1
    assert "default_rotation_schedule" in reasons[0]
    assert "no confirmed Commander CLI setter" in reasons[0]
    assert "--schedule-config only reads config default" in reasons[0]


def test_unsupported_nested_rotation_settings_gate_stays_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider(monkeypatch)

    reasons = provider.unsupported_capabilities(_rotation_manifest())

    assert len(reasons) == 1
    assert "resources[].users[].rotation_settings" in reasons[0]
    assert "pam rotation edit" in reasons[0]


def test_unsupported_nested_rotation_settings_opens_with_experimental_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider(monkeypatch)
    monkeypatch.setenv("DSK_EXPERIMENTAL_ROTATION_APPLY", "1")

    assert provider.unsupported_capabilities(_rotation_manifest()) == []


def test_unsupported_top_level_rotation_stays_closed_with_experimental_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider(monkeypatch)
    monkeypatch.setenv("DSK_EXPERIMENTAL_ROTATION_APPLY", "1")

    reasons = provider.unsupported_capabilities(
        {
            "version": "1",
            "name": "customer-prod",
            "users": [
                {
                    "uid_ref": "usr.top",
                    "type": "pamUser",
                    "title": "top-user",
                    "rotation_settings": {"rotation": "general", "enabled": "on"},
                }
            ],
        }
    )

    assert len(reasons) == 1
    assert "top-level users[].rotation_settings" in reasons[0]


def test_build_post_import_tuning_argvs_for_connection_declared_subset() -> None:
    resource = {
        "type": "pamMachine",
        "pam_configuration_uid_ref": "cfg.local",
        "pam_settings": {
            "options": {
                "connections": "on",
                "graphical_session_recording": "off",
                "text_session_recording": "on",
            },
            "connection": {
                "administrative_credentials_uid_ref": "usr.admin",
                "launch_credentials_uid_ref": "usr.launch",
                "protocol": "rdp",
                "port": 3389,
                "recording_include_keys": False,
            },
        },
    }

    argvs = build_post_import_tuning_argvs(
        "RES_UID",
        resource,
        resolved_refs={
            "cfg.local": "CFG_UID",
            "usr.admin": "ADMIN_UID",
            "usr.launch": "LAUNCH_UID",
        },
    )

    assert argvs == [
        [
            "pam",
            "connection",
            "edit",
            "--configuration",
            "CFG_UID",
            "--connections",
            "on",
            "--connections-recording",
            "off",
            "--typescript-recording",
            "on",
            "--admin-user",
            "ADMIN_UID",
            "--launch-user",
            "LAUNCH_UID",
            "--protocol",
            "rdp",
            "--connections-override-port",
            "3389",
            "--key-events",
            "off",
            "RES_UID",
        ]
    ]


def test_build_post_import_tuning_argvs_for_rbi_declared_subset() -> None:
    resource = {
        "type": "pamRemoteBrowser",
        "pam_configuration_uid_ref": "cfg.local",
        "pam_settings": {
            "options": {
                "remote_browser_isolation": "on",
                "graphical_session_recording": "on",
            },
            "connection": {
                "autofill_credentials_uid_ref": "login.portal",
                "autofill_targets": ["#username", "#password"],
                "allow_url_manipulation": False,
                "allowed_url_patterns": "https://portal.example/*",
                "allowed_resource_url_patterns": ["https://cdn.example/*"],
                "recording_include_keys": True,
                "disable_copy": True,
                "disable_paste": False,
                "ignore_server_cert": True,
            },
        },
    }

    argvs = build_post_import_tuning_argvs(
        "RBI_UID",
        resource,
        resolved_refs={"cfg.local": "CFG_UID", "login.portal": "LOGIN_UID"},
    )

    assert argvs == [
        [
            "pam",
            "rbi",
            "edit",
            "--record",
            "RBI_UID",
            "--configuration",
            "CFG_UID",
            "--remote-browser-isolation",
            "on",
            "--connections-recording",
            "on",
            "--autofill-credentials",
            "LOGIN_UID",
            "--autofill-targets",
            "#username",
            "--autofill-targets",
            "#password",
            "--allow-url-navigation",
            "off",
            "--allowed-urls",
            "https://portal.example/*",
            "--allowed-resource-urls",
            "https://cdn.example/*",
            "--key-events",
            "on",
            "--allow-copy",
            "off",
            "--allow-paste",
            "on",
            "--ignore-server-cert",
            "on",
        ]
    ]


def test_build_post_import_tuning_argvs_requires_resolved_refs() -> None:
    resource = {
        "type": "pamMachine",
        "pam_settings": {
            "connection": {"administrative_credentials_uid_ref": "usr.admin"},
        },
    }

    with pytest.raises(ValueError, match="unresolved uid_ref 'usr.admin'"):
        build_post_import_tuning_argvs("RES_UID", resource)


def _apply_recorder(
    calls: list[list[str]],
    *,
    project_name: str = "customer-prod",
    discovered_entries: object | None = None,
    get_payload: object | None = None,
    get_payloads: dict[str, object] | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
):
    if monkeypatch is not None:
        _install_fake_write_marker(monkeypatch, calls)
    command_map = _resolved_tree_entries(project_name=project_name)
    command_map[("ls", "resources-folder", "--format", "json")] = (
        discovered_entries
        if discovered_entries is not None
        else [
            {
                "type": "record",
                "uid": "keeper-created-uid",
                "name": "db-prod",
                "details": "Type: pamDatabase, Description: ...",
            }
        ]
    )

    def recorder(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        if args[:3] == ["pam", "project", "import"]:
            return ""
        if args[:3] in (["pam", "connection", "edit"], ["pam", "rbi", "edit"]):
            return ""
        key = tuple(args)
        if key in command_map:
            payload = command_map[key]
            return json.dumps(payload) if not isinstance(payload, str) else payload
        if args[:1] == ["get"]:
            payload = get_payloads.get(args[1]) if get_payloads is not None else get_payload
            if payload is None:
                raise AssertionError(f"unexpected get uid {args[1]}")
            return json.dumps(payload) if not isinstance(payload, str) else payload
        if args[:2] == ["record-update", "--record"]:
            return ""
        if args[:3] == ["rm", "--force", "DEL_UID"]:
            return ""
        raise AssertionError(f"unexpected command: {args}")

    return recorder


def _rotation_apply_plan() -> Plan:
    return Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="cfg.local",
                resource_type="pam_configuration",
                title="Lab Config",
                after={"title": "Lab Config"},
            ),
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="res.db",
                resource_type="pamDatabase",
                title="db-prod",
                after={"title": "db-prod"},
            ),
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="usr.db",
                resource_type="pamUser",
                title="db-user",
                after={"title": "db-user"},
            ),
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="usr.admin",
                resource_type="pamUser",
                title="admin-user",
                after={"title": "admin-user"},
            ),
        ],
        order=["cfg.local", "res.db", "usr.db", "usr.admin"],
    )


def _rotation_apply_run_recorder(calls: list[list[str]]):
    command_map = _resolved_tree_entries(project_name="customer-prod")

    def recorder(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        if args[:3] == ["pam", "project", "import"]:
            return ""
        if args[:3] in (["pam", "connection", "edit"], ["pam", "rotation", "edit"]):
            return ""
        key = tuple(args)
        if key in command_map:
            return json.dumps(command_map[key])
        raise AssertionError(f"unexpected command: {args}")

    return recorder


def test_apply_runs_nested_rotation_after_post_import_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setenv("DSK_EXPERIMENTAL_ROTATION_APPLY", "1")
    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _rotation_apply_run_recorder(calls),
    )
    _install_fake_write_marker(monkeypatch, calls)

    def fake_discover(self: CommanderCliProvider) -> list[LiveRecord]:
        calls.append(["__discover__"])
        return _rotation_live_records()

    monkeypatch.setattr(CommanderCliProvider, "discover", fake_discover)
    provider = CommanderCliProvider(folder_uid="folder-uid", manifest_source=_rotation_manifest())

    outcomes = provider.apply_plan(_rotation_apply_plan())

    rotation_call = next(call for call in calls if call[:3] == ["pam", "rotation", "edit"])
    assert calls.index(["__discover__"]) < calls.index(rotation_call)
    assert rotation_call == [
        "pam",
        "rotation",
        "edit",
        "--record",
        "USER_UID",
        "--config",
        "CFG_UID",
        "--resource",
        "RES_UID",
        "--admin-user",
        "ADMIN_UID",
        "--rotation-profile",
        "general",
        "--schedulecron",
        "30 18 * * *",
        "--complexity",
        "32,5,5,5,5",
        "--enable",
        "--force",
    ]
    rotation_outcomes = [outcome for outcome in outcomes if outcome.action == "rotation"]
    assert len(rotation_outcomes) == 1
    assert rotation_outcomes[0].uid_ref == "usr.db"
    assert rotation_outcomes[0].keeper_uid == "USER_UID"
    assert rotation_outcomes[0].details["command"] == rotation_call


def test_apply_uses_unique_title_parent_type_fallback_for_marker_tuning_and_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.utc_timestamp", lambda: "2026-04-24T12:34:56Z"
    )
    monkeypatch.setenv("DSK_EXPERIMENTAL_ROTATION_APPLY", "1")
    manifest = _rotation_manifest()
    manifest["resources"][0]["type"] = "pamMachine"
    manifest["resources"][0]["pam_settings"] = {"options": {"connections": "off"}}
    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _rotation_apply_run_recorder(calls),
    )
    _install_fake_write_marker(monkeypatch, calls)

    def fake_discover(self: CommanderCliProvider) -> list[LiveRecord]:
        calls.append(["__discover__"])
        return [
            LiveRecord(
                keeper_uid="CFG_UID",
                title="Lab Config",
                resource_type="pam_configuration",
            ),
            LiveRecord(
                keeper_uid="RES_UID",
                title="db-prod",
                resource_type="pamDatabase",
            ),
            LiveRecord(
                keeper_uid="USER_UID",
                title="db-user",
                resource_type="pamUser",
            ),
            LiveRecord(
                keeper_uid="ADMIN_UID",
                title="admin-user",
                resource_type="pamUser",
            ),
        ]

    monkeypatch.setattr(CommanderCliProvider, "discover", fake_discover)
    provider = CommanderCliProvider(folder_uid="folder-uid", manifest_source=manifest)
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="cfg.local",
                resource_type="pam_configuration",
                title="Lab Config",
                after={"title": "Lab Config"},
            ),
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="res.db",
                resource_type="pamMachine",
                title="db-prod",
                after={"title": "db-prod"},
            ),
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="usr.db",
                resource_type="pamUser",
                title="db-user",
                after={"title": "db-user"},
            ),
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="usr.admin",
                resource_type="pamUser",
                title="admin-user",
                after={"title": "admin-user"},
            ),
        ],
        order=["cfg.local", "res.db", "usr.db", "usr.admin"],
    )

    outcomes = provider.apply_plan(plan)

    tuning_call = [
        "pam",
        "connection",
        "edit",
        "--configuration",
        "CFG_UID",
        "--connections",
        "off",
        "RES_UID",
    ]
    rotation_call = [
        "pam",
        "rotation",
        "edit",
        "--record",
        "USER_UID",
        "--config",
        "CFG_UID",
        "--resource",
        "RES_UID",
        "--admin-user",
        "ADMIN_UID",
        "--rotation-profile",
        "general",
        "--schedulecron",
        "30 18 * * *",
        "--complexity",
        "32,5,5,5,5",
        "--enable",
        "--force",
    ]
    assert tuning_call in calls
    assert rotation_call in calls
    parent_marker_call = next(
        call for call in calls if call[:3] == ["record-update", "--record", "RES_UID"]
    )
    _, payload = parent_marker_call[4].split("=", 1)
    assert json.loads(payload) == encode_marker(
        uid_ref="res.db",
        manifest="customer-prod",
        resource_type="pamMachine",
        last_applied_at="2026-04-24T12:34:56Z",
    )
    outcomes_by_ref = {outcome.uid_ref: outcome for outcome in outcomes if outcome.uid_ref}
    assert outcomes_by_ref["res.db"].details["post_import_tuning_argvs"] == [tuning_call]
    assert outcomes_by_ref["res.db"].details["marker_written"] is True


def test_apply_rejects_duplicate_title_parent_type_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _rotation_apply_run_recorder(calls),
    )

    def fake_discover(self: CommanderCliProvider) -> list[LiveRecord]:
        return [
            LiveRecord(
                keeper_uid="RES_UID_1",
                title="machine-prod",
                resource_type="pamDatabase",
            ),
            LiveRecord(
                keeper_uid="RES_UID_2",
                title="machine-prod",
                resource_type="pamDirectory",
            ),
        ]

    monkeypatch.setattr(CommanderCliProvider, "discover", fake_discover)
    provider = CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source={
            "version": "1",
            "name": "customer-prod",
            "resources": [{"uid_ref": "res.host", "type": "pamMachine", "title": "machine-prod"}],
        },
    )
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="res.host",
                resource_type="pamMachine",
                title="machine-prod",
                after={"title": "machine-prod"},
            )
        ],
        order=["res.host"],
    )

    with pytest.raises(CollisionError, match="live tenant has 2 records titled 'machine-prod'"):
        provider.apply_plan(plan)


def test_apply_rotation_dry_run_does_not_execute_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setenv("DSK_EXPERIMENTAL_ROTATION_APPLY", "1")
    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _rotation_apply_run_recorder(calls),
    )
    monkeypatch.setattr(
        CommanderCliProvider,
        "discover",
        lambda self: pytest.fail("dry-run must not discover live records"),
    )
    provider = CommanderCliProvider(folder_uid="folder-uid", manifest_source=_rotation_manifest())

    outcomes = provider.apply_plan(_rotation_apply_plan(), dry_run=True)

    assert all(call[:3] != ["pam", "rotation", "edit"] for call in calls)
    assert all(call != ["__discover__"] for call in calls)
    assert calls[0][:3] == ["pam", "project", "import"]
    assert calls[0][-1] == "--dry-run"
    assert {outcome.action for outcome in outcomes} == {"create"}
    outcomes_by_ref = {outcome.uid_ref: outcome for outcome in outcomes}
    assert outcomes_by_ref["cfg.local"].details == {"dry_run": True}
    assert outcomes_by_ref["res.db"].details == {"dry_run": True}
    assert outcomes_by_ref["usr.admin"].details == {"dry_run": True}
    assert outcomes_by_ref["usr.db"].details == {
        "dry_run": True,
        "rotation_argvs": [
            [
                "pam",
                "rotation",
                "edit",
                "--record",
                "<record:usr.db>",
                "--config",
                "<uid_ref:cfg.local>",
                "--resource",
                "<uid_ref:res.db>",
                "--admin-user",
                "<uid_ref:usr.admin>",
                "--rotation-profile",
                "general",
                "--schedulecron",
                "30 18 * * *",
                "--complexity",
                "32,5,5,5,5",
                "--enable",
                "--force",
            ]
        ],
        "rotation_dry_run": True,
    }


def test_apply_rotation_dry_run_stays_blocked_without_experimental_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.delenv("DSK_EXPERIMENTAL_ROTATION_APPLY", raising=False)
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        lambda self, args: pytest.fail(f"unexpected command: {args}"),
    )
    provider = CommanderCliProvider(folder_uid="folder-uid", manifest_source=_rotation_manifest())

    with pytest.raises(CapabilityError) as exc_info:
        provider.apply_plan(_rotation_apply_plan(), dry_run=True)

    assert "resources[].users[].rotation_settings is not implemented" in exc_info.value.reason
    assert "DSK_EXPERIMENTAL_ROTATION_APPLY=1" in exc_info.value.reason


def test_apply_rotation_missing_live_ref_becomes_capability_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setenv("DSK_EXPERIMENTAL_ROTATION_APPLY", "1")
    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _rotation_apply_run_recorder(calls),
    )
    _install_fake_write_marker(monkeypatch, calls)

    def fake_discover(self: CommanderCliProvider) -> list[LiveRecord]:
        return [record for record in _rotation_live_records() if record.keeper_uid != "USER_UID"]

    monkeypatch.setattr(CommanderCliProvider, "discover", fake_discover)
    provider = CommanderCliProvider(folder_uid="folder-uid", manifest_source=_rotation_manifest())

    with pytest.raises(CapabilityError) as exc_info:
        provider.apply_plan(_rotation_apply_plan())

    assert "cannot apply resources[].users[].rotation_settings" in exc_info.value.reason
    assert "missing live nested pamUser" in exc_info.value.reason
    assert "pam project import/extend created" in exc_info.value.next_action


def test_discover_requires_folder_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    provider = CommanderCliProvider(folder_uid=None)

    with pytest.raises(CapabilityError) as exc_info:
        provider.discover()

    assert "run apply_plan() first" in exc_info.value.reason
    assert (
        exc_info.value.next_action
        == "pass --folder-uid (or KEEPER_DECLARATIVE_FOLDER), or call apply_plan() first"
    )


def test_discover_empty_folder_returns_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _discover_provider(monkeypatch, ls_payload=[])

    records = provider.discover()

    assert records == []


def test_discover_reads_one_record_without_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _discover_provider(
        monkeypatch,
        ls_payload=[
            {
                "type": "record",
                "uid": "R1",
                "name": "host1",
                "details": "Type: pamMachine, Description: machine",
            }
        ],
        get_payloads={
            "R1": {
                "record_uid": "R1",
                "title": "host1",
                "type": "pamMachine",
                "fields": [{"type": "host", "value": [{"hostName": "h", "port": "22"}]}],
                "custom": [],
            }
        },
    )

    records = provider.discover()

    assert len(records) == 1
    assert records[0].keeper_uid == "R1"
    assert records[0].title == "host1"
    assert records[0].resource_type == "pamMachine"
    assert records[0].marker is None
    assert records[0].payload["host"] == "h"
    assert records[0].payload["port"] == "22"


def test_discover_decodes_marker_from_custom_field(monkeypatch: pytest.MonkeyPatch) -> None:
    marker = serialize_marker(
        encode_marker(
            uid_ref="host1",
            manifest="prod",
            resource_type="pamMachine",
        )
    )
    provider = _discover_provider(
        monkeypatch,
        ls_payload=[
            {
                "type": "record",
                "uid": "R1",
                "name": "host1",
                "details": "Type: pamMachine, Description: machine",
            }
        ],
        get_payloads={
            "R1": {
                "record_uid": "R1",
                "title": "host1",
                "type": "pamMachine",
                "fields": [],
                "custom": [
                    {"type": "text", "label": "keeper_declarative_manager", "value": [marker]}
                ],
            }
        },
    )

    records = provider.discover()

    assert records[0].marker is not None
    assert records[0].marker["uid_ref"] == "host1"


def test_discover_ignores_folder_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _discover_provider(
        monkeypatch,
        ls_payload=[
            {"type": "folder", "uid": "F1", "name": "nested", "details": "Folder"},
            {
                "type": "record",
                "uid": "R1",
                "name": "host1",
                "details": "Type: pamMachine, Description: ...",
            },
        ],
        get_payloads={
            "R1": {
                "record_uid": "R1",
                "title": "host1",
                "type": "pamMachine",
                "fields": [],
                "custom": [],
            }
        },
    )

    records = provider.discover()

    assert [record.keeper_uid for record in records] == ["R1"]


def test_discover_uses_ls_details_when_get_type_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _discover_provider(
        monkeypatch,
        ls_payload=[
            {
                "type": "record",
                "uid": "R1",
                "name": "svc-admin",
                "details": "Type: pamUser, Description: ...",
            }
        ],
        get_payloads={
            "R1": {
                "record_uid": "R1",
                "title": "svc-admin",
                "fields": [],
                "custom": [],
            }
        },
    )

    records = provider.discover()

    assert records[0].resource_type == "pamUser"


def test_discover_reads_project_resources_and_users_with_dedupe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    calls: list[list[str]] = []

    def recorder(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        if args == ["ls", "--format", "json", "PAM Environments"]:
            return json.dumps(
                [{"type": "folder", "uid": "project-folder", "name": "customer-prod"}]
            )
        if args == ["ls", "--format", "json", "project-folder"]:
            return json.dumps(
                [
                    {
                        "type": "folder",
                        "uid": "resources-folder",
                        "name": "customer-prod - Resources",
                    },
                    {"type": "folder", "uid": "users-folder", "name": "customer-prod - Users"},
                ]
            )
        if args == ["ls", "resources-folder", "--format", "json"]:
            return json.dumps(
                [
                    {
                        "type": "record",
                        "uid": "MACHINE_UID",
                        "name": "machine-prod",
                        "details": "Type: pamMachine, Description: ...",
                    },
                    {
                        "type": "record",
                        "uid": "DUP_UID",
                        "name": "shared-admin",
                        "details": "Type: pamUser, Description: ...",
                    },
                ]
            )
        if args == ["ls", "users-folder", "--format", "json"]:
            return json.dumps(
                [
                    {
                        "type": "record",
                        "uid": "DUP_UID",
                        "name": "shared-admin",
                        "details": "Type: pamUser, Description: ...",
                    },
                    {
                        "type": "record",
                        "uid": "ADMIN_UID",
                        "name": "admin-user",
                        "details": "Type: pamUser, Description: ...",
                    },
                ]
            )
        if args[:1] == ["get"]:
            uid = args[1]
            title = {"MACHINE_UID": "machine-prod", "DUP_UID": "shared-admin"}.get(
                uid, "admin-user"
            )
            return json.dumps(
                {
                    "record_uid": uid,
                    "title": title,
                    "type": "pamMachine" if uid == "MACHINE_UID" else "pamUser",
                    "fields": [],
                    "custom": [],
                }
            )
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", recorder)
    provider = CommanderCliProvider(
        folder_uid=None,
        manifest_source={"version": "1", "name": "customer-prod"},
    )

    records = provider.discover()

    assert [record.keeper_uid for record in records] == ["MACHINE_UID", "DUP_UID", "ADMIN_UID"]
    assert [call for call in calls if call == ["get", "DUP_UID", "--format", "json"]] == [
        ["get", "DUP_UID", "--format", "json"]
    ]
    assert provider.last_resolved_folder_uid == "resources-folder"
    assert provider.last_resolved_users_folder_uid == "users-folder"


def test_discover_raises_on_non_json_ls(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch, "not json")

    with pytest.raises(CapabilityError) as exc_info:
        provider.discover()

    assert exc_info.value.reason == "Commander returned non-JSON from `ls --format json`"


def test_resolve_project_resources_folder_walks_pam_environments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _apply_recorder(
            calls, project_name="customer-prod", discovered_entries=[], monkeypatch=monkeypatch
        ),
    )
    provider = CommanderCliProvider(folder_uid=None)

    resolved = provider._resolve_project_resources_folder("customer-prod")

    assert resolved == "resources-folder"
    assert provider.last_resolved_folder_uid == "resources-folder"
    assert calls == [
        ["ls", "--format", "json", "PAM Environments"],
        ["ls", "--format", "json", "project-folder"],
    ]


def test_apply_writes_marker_after_create(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.utc_timestamp", lambda: "2026-04-24T12:34:56Z"
    )

    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _apply_recorder(
            calls,
            project_name="customer-prod",
            get_payload={
                "record_uid": "keeper-created-uid",
                "title": "db-prod",
                "type": "pamDatabase",
                "fields": [],
                "custom": [],
            },
            monkeypatch=monkeypatch,
        ),
    )
    provider = CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source={
            "version": "1",
            "name": "customer-prod",
            "resources": [{"uid_ref": "prod-db", "type": "pamDatabase", "title": "db-prod"}],
        },
    )
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="prod-db",
                resource_type="pamDatabase",
                title="db-prod",
                after={"title": "db-prod"},
            )
        ],
        order=["prod-db"],
    )

    outcomes = provider.apply_plan(plan)

    assert calls[:7] == [
        ["pam", "project", "import", "--file", calls[0][4], "--name", "customer-prod"],
        ["ls", "--format", "json", "PAM Environments"],
        ["ls", "--format", "json", "project-folder"],
        ["ls", "--format", "json", "PAM Environments"],
        ["ls", "--format", "json", "project-folder"],
        ["ls", "resources-folder", "--format", "json"],
        ["get", "keeper-created-uid", "--format", "json"],
    ]
    assert calls[7][:3] == ["record-update", "--record", "keeper-created-uid"]
    assert provider.last_resolved_folder_uid == "resources-folder"
    assert outcomes[0].details["marker_written"] is True
    assert outcomes[0].details["keeper_uid"] == "keeper-created-uid"
    assert outcomes[0].details["verified"] is True
    assert "field_drift" not in outcomes[0].details
    assert calls[-1][:4] == ["record-update", "--record", "keeper-created-uid", "-cf"]
    label, payload = calls[-1][4].split("=", 1)
    assert label == "keeper_declarative_manager"
    assert json.loads(payload) == encode_marker(
        uid_ref="prod-db",
        manifest="customer-prod",
        resource_type="pamDatabase",
        last_applied_at="2026-04-24T12:34:56Z",
    )


def test_apply_dry_run_skips_marker_writeback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    calls: list[list[str]] = []

    def recorder(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        return ""

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", recorder)
    provider = CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source={
            "version": "1",
            "name": "customer-prod",
            "resources": [{"uid_ref": "prod-db", "type": "pamDatabase", "title": "db-prod"}],
        },
    )
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="prod-db",
                resource_type="pamDatabase",
                title="db-prod",
                after={"title": "db-prod"},
            )
        ],
        order=["prod-db"],
    )

    outcomes = provider.apply_plan(plan, dry_run=True)

    assert outcomes[0].details == {"dry_run": True}
    assert all(call[0] != "record-update" for call in calls)
    assert all(call[:1] != ["ls"] for call in calls)


def test_apply_dry_run_exposes_post_import_tuning_without_executing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    calls: list[list[str]] = []

    def recorder(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        return ""

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", recorder)
    provider = CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source={
            "version": "1",
            "name": "customer-prod",
            "resources": [
                {
                    "uid_ref": "prod-machine",
                    "type": "pamMachine",
                    "title": "machine-prod",
                    "pam_settings": {"options": {"connections": "off"}},
                }
            ],
        },
    )
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="prod-machine",
                resource_type="pamMachine",
                title="machine-prod",
                after={"title": "machine-prod"},
            )
        ],
        order=["prod-machine"],
    )

    outcomes = provider.apply_plan(plan, dry_run=True)

    assert all(call[:3] != ["pam", "connection", "edit"] for call in calls)
    assert outcomes[0].details == {
        "dry_run": True,
        "post_import_tuning_argvs": [
            [
                "pam",
                "connection",
                "edit",
                "--connections",
                "off",
                "<record:prod-machine>",
            ]
        ],
        "post_import_tuning_dry_run": True,
    }


def test_apply_skips_marker_when_record_not_discoverable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _apply_recorder(
            calls, project_name="customer-prod", discovered_entries=[], monkeypatch=monkeypatch
        ),
    )
    provider = CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source={
            "version": "1",
            "name": "customer-prod",
            "resources": [{"uid_ref": "prod-db", "type": "pamDatabase", "title": "db-prod"}],
        },
    )
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="prod-db",
                resource_type="pamDatabase",
                title="db-prod",
                after={"title": "db-prod"},
            )
        ],
        order=["prod-db"],
    )

    outcomes = provider.apply_plan(plan)

    assert outcomes[0].details["marker_written"] is False
    assert outcomes[0].details["reason"] == "record not found after apply"
    assert all(call[0] != "record-update" for call in calls)


def test_apply_verifies_fields_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.utc_timestamp", lambda: "2026-04-24T12:34:56Z"
    )

    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _apply_recorder(
            calls,
            project_name="customer-prod",
            get_payload={
                "record_uid": "keeper-created-uid",
                "title": "db-prod",
                "type": "pamDatabase",
                "fields": [
                    {"type": "host", "value": [{"hostName": "db.example.com", "port": 5432}]}
                ],
                "custom": [],
            },
            monkeypatch=monkeypatch,
        ),
    )
    provider = CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source={
            "version": "1",
            "name": "customer-prod",
            "resources": [
                {
                    "uid_ref": "prod-db",
                    "type": "pamDatabase",
                    "title": "db-prod",
                    "host": "db.example.com",
                    "port": 5432,
                }
            ],
        },
    )
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="prod-db",
                resource_type="pamDatabase",
                title="db-prod",
                after={"title": "db-prod", "host": "db.example.com", "port": "5432"},
            )
        ],
        order=["prod-db"],
    )

    outcomes = provider.apply_plan(plan)

    assert calls[:7] == [
        ["pam", "project", "import", "--file", calls[0][4], "--name", "customer-prod"],
        ["ls", "--format", "json", "PAM Environments"],
        ["ls", "--format", "json", "project-folder"],
        ["ls", "--format", "json", "PAM Environments"],
        ["ls", "--format", "json", "project-folder"],
        ["ls", "resources-folder", "--format", "json"],
        ["get", "keeper-created-uid", "--format", "json"],
    ]
    assert calls[7][:3] == ["record-update", "--record", "keeper-created-uid"]
    assert outcomes[0].details["marker_written"] is True
    assert outcomes[0].details["verified"] is True
    assert "field_drift" not in outcomes[0].details


def test_apply_executes_post_import_connection_tuning_after_rediscovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.utc_timestamp", lambda: "2026-04-24T12:34:56Z"
    )

    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _apply_recorder(
            calls,
            project_name="customer-prod",
            discovered_entries=[
                {
                    "type": "record",
                    "uid": "MACHINE_UID",
                    "name": "machine-prod",
                    "details": "Type: pamMachine, Description: ...",
                },
                {
                    "type": "record",
                    "uid": "CFG_UID",
                    "name": "Local Config",
                    "details": "Type: pam_configuration, Description: ...",
                },
                {
                    "type": "record",
                    "uid": "ADMIN_UID",
                    "name": "admin-user",
                    "details": "Type: pamUser, Description: ...",
                },
                {
                    "type": "record",
                    "uid": "LAUNCH_UID",
                    "name": "launch-user",
                    "details": "Type: pamUser, Description: ...",
                },
            ],
            get_payloads={
                "MACHINE_UID": {
                    "record_uid": "MACHINE_UID",
                    "title": "machine-prod",
                    "type": "pamMachine",
                    "fields": [],
                    "custom": [],
                },
                "CFG_UID": {
                    "record_uid": "CFG_UID",
                    "title": "Local Config",
                    "type": "pam_configuration",
                    "fields": [],
                    "custom": [],
                },
                "ADMIN_UID": {
                    "record_uid": "ADMIN_UID",
                    "title": "admin-user",
                    "type": "pamUser",
                    "fields": [],
                    "custom": [],
                },
                "LAUNCH_UID": {
                    "record_uid": "LAUNCH_UID",
                    "title": "launch-user",
                    "type": "pamUser",
                    "fields": [],
                    "custom": [],
                },
            },
            monkeypatch=monkeypatch,
        ),
    )
    provider = CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source={
            "version": "1",
            "name": "customer-prod",
            "pam_configurations": [{"uid_ref": "cfg.local", "title": "Local Config"}],
            "resources": [
                {
                    "uid_ref": "prod-machine",
                    "type": "pamMachine",
                    "title": "machine-prod",
                    "pam_configuration_uid_ref": "cfg.local",
                    "pam_settings": {
                        "options": {"connections": "on"},
                        "connection": {
                            "administrative_credentials_uid_ref": "usr.admin",
                            "launch_credentials_uid_ref": "usr.launch",
                            "port": 22,
                            "recording_include_keys": True,
                        },
                    },
                    "users": [
                        {"uid_ref": "usr.admin", "type": "pamUser", "title": "admin-user"},
                        {"uid_ref": "usr.launch", "type": "pamUser", "title": "launch-user"},
                    ],
                }
            ],
        },
    )
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="prod-machine",
                resource_type="pamMachine",
                title="machine-prod",
                after={"title": "machine-prod"},
            )
        ],
        order=["prod-machine"],
    )

    outcomes = provider.apply_plan(plan)

    expected = [
        "pam",
        "connection",
        "edit",
        "--configuration",
        "CFG_UID",
        "--connections",
        "on",
        "--admin-user",
        "ADMIN_UID",
        "--launch-user",
        "LAUNCH_UID",
        "--connections-override-port",
        "22",
        "--key-events",
        "on",
        "MACHINE_UID",
    ]
    assert expected in calls
    assert calls.index(expected) < next(
        idx for idx, call in enumerate(calls) if call[:2] == ["record-update", "--record"]
    )
    assert outcomes[0].details["post_import_tuning_argvs"] == [expected]
    assert outcomes[0].details["post_import_tuning_executed"] is True
    assert outcomes[0].details["marker_written"] is True


def test_apply_executes_post_import_rbi_tuning_after_rediscovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.utc_timestamp", lambda: "2026-04-24T12:34:56Z"
    )

    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _apply_recorder(
            calls,
            project_name="customer-prod",
            discovered_entries=[
                {
                    "type": "record",
                    "uid": "RBI_UID",
                    "name": "portal",
                    "details": "Type: pamRemoteBrowser, Description: ...",
                },
                {
                    "type": "record",
                    "uid": "CFG_UID",
                    "name": "Local Config",
                    "details": "Type: pam_configuration, Description: ...",
                },
                {
                    "type": "record",
                    "uid": "LOGIN_UID",
                    "name": "portal-login",
                    "details": "Type: login, Description: ...",
                },
            ],
            get_payloads={
                "RBI_UID": {
                    "record_uid": "RBI_UID",
                    "title": "portal",
                    "type": "pamRemoteBrowser",
                    "fields": [],
                    "custom": [],
                },
                "CFG_UID": {
                    "record_uid": "CFG_UID",
                    "title": "Local Config",
                    "type": "pam_configuration",
                    "fields": [],
                    "custom": [],
                },
                "LOGIN_UID": {
                    "record_uid": "LOGIN_UID",
                    "title": "portal-login",
                    "type": "login",
                    "fields": [],
                    "custom": [],
                },
            },
            monkeypatch=monkeypatch,
        ),
    )
    provider = CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source={
            "version": "1",
            "name": "customer-prod",
            "pam_configurations": [{"uid_ref": "cfg.local", "title": "Local Config"}],
            "resources": [
                {
                    "uid_ref": "portal",
                    "type": "pamRemoteBrowser",
                    "title": "portal",
                    "pam_configuration_uid_ref": "cfg.local",
                    "pam_settings": {
                        "options": {"remote_browser_isolation": "on"},
                        "connection": {
                            "autofill_credentials_uid_ref": "login.portal",
                            "disable_copy": True,
                            "ignore_server_cert": False,
                        },
                    },
                },
                {"uid_ref": "login.portal", "type": "login", "title": "portal-login"},
            ],
        },
    )
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="portal",
                resource_type="pamRemoteBrowser",
                title="portal",
                after={"title": "portal"},
            )
        ],
        order=["portal"],
    )

    outcomes = provider.apply_plan(plan)

    expected = [
        "pam",
        "rbi",
        "edit",
        "--record",
        "RBI_UID",
        "--configuration",
        "CFG_UID",
        "--remote-browser-isolation",
        "on",
        "--autofill-credentials",
        "LOGIN_UID",
        "--allow-copy",
        "off",
        "--ignore-server-cert",
        "off",
    ]
    assert expected in calls
    assert outcomes[0].details["post_import_tuning_argvs"] == [expected]
    assert outcomes[0].details["post_import_tuning_executed"] is True


def test_apply_post_import_tuning_raises_on_unresolved_credential_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _apply_recorder(
            calls,
            project_name="customer-prod",
            discovered_entries=[
                {
                    "type": "record",
                    "uid": "MACHINE_UID",
                    "name": "machine-prod",
                    "details": "Type: pamMachine, Description: ...",
                }
            ],
            get_payloads={
                "MACHINE_UID": {
                    "record_uid": "MACHINE_UID",
                    "title": "machine-prod",
                    "type": "pamMachine",
                    "fields": [],
                    "custom": [],
                }
            },
            monkeypatch=monkeypatch,
        ),
    )
    provider = CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source={
            "version": "1",
            "name": "customer-prod",
            "resources": [
                {
                    "uid_ref": "prod-machine",
                    "type": "pamMachine",
                    "title": "machine-prod",
                    "pam_settings": {
                        "connection": {
                            "administrative_credentials_uid_ref": "usr.admin",
                        }
                    },
                    "users": [{"uid_ref": "usr.admin", "type": "pamUser", "title": "admin-user"}],
                }
            ],
        },
    )
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="prod-machine",
                resource_type="pamMachine",
                title="machine-prod",
                after={"title": "machine-prod"},
            )
        ],
        order=["prod-machine"],
    )

    with pytest.raises(CapabilityError) as exc_info:
        provider.apply_plan(plan)

    assert "post-import tuning could not resolve refs" in exc_info.value.reason
    assert "usr.admin" in exc_info.value.reason
    assert all(call[:2] != ["record-update", "--record"] for call in calls)


def test_apply_post_import_tuning_resolves_user_from_project_users_folder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.utc_timestamp", lambda: "2026-04-24T12:34:56Z"
    )

    calls: list[list[str]] = []
    project_entries = [
        {"type": "folder", "uid": "resources-folder", "name": "customer-prod - Resources"},
        {"type": "folder", "uid": "users-folder", "name": "customer-prod - Users"},
    ]

    def recorder(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        if args == ["ls", "--format", "json", "PAM Environments"]:
            return json.dumps(
                [{"type": "folder", "uid": "project-folder", "name": "customer-prod"}]
            )
        if args in (
            ["ls", "--format", "json", "PAM Environments/customer-prod"],
            ["ls", "--format", "json", "project-folder"],
        ):
            return json.dumps(project_entries)
        if args in (
            [
                "ls",
                "--format",
                "json",
                "PAM Environments/customer-prod/customer-prod - Resources",
            ],
            [
                "ls",
                "--format",
                "json",
                "PAM Environments/customer-prod/customer-prod - Users",
            ],
        ):
            return json.dumps([])
        if args[:4] == ["secrets-manager", "share", "add", "--app"]:
            return ""
        if args == ["pam", "gateway", "list", "--format", "json"]:
            return json.dumps(
                {
                    "gateways": [
                        {
                            "ksm_app_name": "Lab GW Application",
                            "ksm_app_uid": "APP_UID",
                            "gateway_name": "Lab GW Rocky",
                            "gateway_uid": "GW_UID",
                        }
                    ]
                }
            )
        if args == ["pam", "config", "list", "--format", "json"]:
            return json.dumps(
                {
                    "configurations": [
                        {
                            "uid": "CFG_UID",
                            "config_name": "Local Config",
                            "shared_folder": {"name": "Lab GW Folder", "uid": "SF_UID"},
                            "gateway_uid": "GW_UID",
                        }
                    ]
                }
            )
        if args[:4] == ["pam", "project", "extend", "--config"]:
            return ""
        if args == ["ls", "resources-folder", "--format", "json"]:
            return json.dumps(
                [
                    {
                        "type": "record",
                        "uid": "MACHINE_UID",
                        "name": "machine-prod",
                        "details": "Type: pamMachine, Description: ...",
                    }
                ]
            )
        if args == ["ls", "users-folder", "--format", "json"]:
            return json.dumps(
                [
                    {
                        "type": "record",
                        "uid": "ADMIN_UID",
                        "name": "admin-user",
                        "details": "Type: pamUser, Description: ...",
                    }
                ]
            )
        if args == ["get", "MACHINE_UID", "--format", "json"]:
            return json.dumps(
                {
                    "record_uid": "MACHINE_UID",
                    "title": "machine-prod",
                    "type": "pamMachine",
                    "fields": [],
                    "custom": [],
                }
            )
        if args == ["get", "ADMIN_UID", "--format", "json"]:
            return json.dumps(
                {
                    "record_uid": "ADMIN_UID",
                    "title": "admin-user",
                    "type": "pamUser",
                    "fields": [],
                    "custom": [],
                }
            )
        if args[:3] == ["pam", "connection", "edit"]:
            return ""
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", recorder)
    _install_fake_write_marker(monkeypatch, calls)
    provider = CommanderCliProvider(
        folder_uid=None,
        manifest_source={
            "version": "1",
            "name": "customer-prod",
            "gateways": [{"uid_ref": "gw", "name": "Lab GW Rocky", "mode": "reference_existing"}],
            "pam_configurations": [
                {
                    "uid_ref": "cfg.local",
                    "title": "Local Config",
                    "environment": "local",
                    "gateway_uid_ref": "gw",
                }
            ],
            "resources": [
                {
                    "uid_ref": "prod-machine",
                    "type": "pamMachine",
                    "title": "machine-prod",
                    "pam_configuration_uid_ref": "cfg.local",
                    "pam_settings": {
                        "options": {"connections": "on"},
                        "connection": {"administrative_credentials_uid_ref": "usr.admin"},
                    },
                    "users": [{"uid_ref": "usr.admin", "type": "pamUser", "title": "admin-user"}],
                }
            ],
        },
    )
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="cfg.local",
                resource_type="pam_configuration",
                title="Local Config",
                after={"title": "Local Config"},
            ),
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="prod-machine",
                resource_type="pamMachine",
                title="machine-prod",
                after={"title": "machine-prod"},
            ),
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="usr.admin",
                resource_type="pamUser",
                title="admin-user",
                after={"title": "admin-user"},
            ),
        ],
        order=["cfg.local", "prod-machine", "usr.admin"],
    )

    outcomes = provider.apply_plan(plan)

    expected = [
        "pam",
        "connection",
        "edit",
        "--configuration",
        "CFG_UID",
        "--connections",
        "on",
        "--admin-user",
        "ADMIN_UID",
        "MACHINE_UID",
    ]
    assert expected in calls
    assert calls.index(["ls", "users-folder", "--format", "json"]) < calls.index(expected)
    outcomes_by_ref = {outcome.uid_ref: outcome for outcome in outcomes}
    assert outcomes_by_ref["prod-machine"].details["post_import_tuning_argvs"] == [expected]
    assert outcomes_by_ref["prod-machine"].details["post_import_tuning_executed"] is True
    assert outcomes_by_ref["usr.admin"].details["marker_written"] is True


def test_apply_post_import_tuning_noop_without_tuning_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _apply_recorder(
            calls,
            project_name="customer-prod",
            get_payload={
                "record_uid": "MACHINE_UID",
                "title": "machine-prod",
                "type": "pamMachine",
                "fields": [],
                "custom": [],
            },
            monkeypatch=monkeypatch,
        ),
    )
    provider = CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source={
            "version": "1",
            "name": "customer-prod",
            "resources": [
                {
                    "uid_ref": "prod-machine",
                    "type": "pamMachine",
                    "title": "machine-prod",
                    "pam_configuration_uid_ref": "cfg.local",
                }
            ],
        },
    )
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="prod-machine",
                resource_type="pamMachine",
                title="machine-prod",
                after={"title": "machine-prod"},
            )
        ],
        order=["prod-machine"],
    )

    outcomes = provider.apply_plan(plan)

    assert all(call[:3] != ["pam", "connection", "edit"] for call in calls)
    assert "post_import_tuning_argvs" not in outcomes[0].details
    assert outcomes[0].details["marker_written"] is True


def test_apply_reports_field_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.utc_timestamp", lambda: "2026-04-24T12:34:56Z"
    )

    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _apply_recorder(
            calls,
            project_name="customer-prod",
            get_payload={
                "record_uid": "keeper-created-uid",
                "title": "db-prod",
                "type": "pamDatabase",
                "fields": [
                    {
                        "type": "host",
                        "value": [{"hostName": "db-observed.example.com", "port": 5432}],
                    }
                ],
                "custom": [],
            },
            monkeypatch=monkeypatch,
        ),
    )
    provider = CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source={
            "version": "1",
            "name": "customer-prod",
            "resources": [
                {
                    "uid_ref": "prod-db",
                    "type": "pamDatabase",
                    "title": "db-prod",
                    "host": "db.example.com",
                    "port": 5432,
                }
            ],
        },
    )
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="prod-db",
                resource_type="pamDatabase",
                title="db-prod",
                after={"title": "db-prod", "host": "db.example.com", "port": "5432"},
            )
        ],
        order=["prod-db"],
    )

    outcomes = provider.apply_plan(plan)

    assert outcomes[0].details["marker_written"] is True
    assert "verified" not in outcomes[0].details
    assert outcomes[0].details["field_drift"] == {
        "host": {
            "expected": "db.example.com",
            "observed": "db-observed.example.com",
        }
    }


def test_apply_deletes_managed_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.utc_timestamp", lambda: "2026-04-24T12:34:56Z"
    )

    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _apply_recorder(
            calls,
            project_name="customer-prod",
            get_payload={
                "record_uid": "keeper-created-uid",
                "title": "db-prod",
                "type": "pamDatabase",
                "fields": [],
                "custom": [],
            },
            monkeypatch=monkeypatch,
        ),
    )
    provider = CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source={
            "version": "1",
            "name": "customer-prod",
            "resources": [{"uid_ref": "prod-db", "type": "pamDatabase", "title": "db-prod"}],
        },
    )
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="prod-db",
                resource_type="pamDatabase",
                title="db-prod",
                after={"title": "db-prod"},
            ),
            Change(
                kind=ChangeKind.DELETE,
                uid_ref="old-db",
                resource_type="pamDatabase",
                title="old-db",
                keeper_uid="DEL_UID",
            ),
        ],
        order=["prod-db", "old-db"],
    )

    outcomes = provider.apply_plan(plan)

    rm_index = calls.index(["rm", "--force", "DEL_UID"])
    import_index = next(
        idx for idx, call in enumerate(calls) if call[:3] == ["pam", "project", "import"]
    )
    assert rm_index > import_index
    assert calls[-1] == ["rm", "--force", "DEL_UID"]
    delete_outcome = next(outcome for outcome in outcomes if outcome.action == "delete")
    assert delete_outcome.keeper_uid == "DEL_UID"
    assert delete_outcome.details["keeper_uid"] == "DEL_UID"
    assert delete_outcome.details["removed"] is True


def test_apply_dry_run_delete_does_not_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    calls: list[list[str]] = []

    def recorder(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        return ""

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", recorder)
    provider = CommanderCliProvider(folder_uid="folder-uid")
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.DELETE,
                uid_ref="old-db",
                resource_type="pamDatabase",
                title="old-db",
                keeper_uid="DEL_UID",
            )
        ],
        order=["old-db"],
    )

    outcomes = provider.apply_plan(plan, dry_run=True)

    assert calls == []
    assert len(outcomes) == 1
    assert outcomes[0].action == "delete"
    assert outcomes[0].details["dry_run"] is True
    assert outcomes[0].details["keeper_uid"] == "DEL_UID"


def test_apply_delete_without_keeper_uid_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    calls: list[list[str]] = []

    def recorder(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        return ""

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", recorder)
    provider = CommanderCliProvider(folder_uid="folder-uid")
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.DELETE,
                uid_ref="old-db",
                resource_type="pamDatabase",
                title="old-db",
                keeper_uid=None,
            )
        ],
        order=["old-db"],
    )

    outcomes = provider.apply_plan(plan)

    assert calls == []
    assert outcomes[0].action == "delete"
    assert outcomes[0].keeper_uid == ""
    assert outcomes[0].details["skipped"] is True
    assert outcomes[0].details["reason"] == "no keeper_uid on delete change"


def test_run_cmd_wraps_in_process_pam_import_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """`pam project import` now runs in-process — a CommandError raised by
    Commander (e.g. missing --name) must surface as a CapabilityError with
    stdout/stderr context preserved so the CLI can display it."""
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    class _FakeCmd:
        def execute(self, params, **kwargs):
            print("about to fail")
            raise RuntimeError("Project name is required")

    fake_module = types.SimpleNamespace(PAMProjectImportCommand=_FakeCmd)
    monkeypatch.setitem(
        sys.modules,
        "keepercommander.commands.pam_import.edit",
        fake_module,
    )

    provider = CommanderCliProvider(folder_uid="folder-uid")
    provider._keeper_params = object()  # bypass real login

    with pytest.raises(CapabilityError) as exc_info:
        provider._run_cmd(["pam", "project", "import", "--file", "/tmp/manifest.json"])

    assert "in-process keeper pam project import failed" in exc_info.value.reason
    assert "Project name is required" in exc_info.value.reason
    assert "about to fail" in exc_info.value.context["stdout"]


def test_run_cmd_refreshes_session_once_on_keeper_api_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from keepercommander.error import KeeperApiError

    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    params = [object(), object()]
    login_states: list[tuple[object | None, bool]] = []
    seen_params: list[object] = []

    def fake_get_params(self: CommanderCliProvider) -> object:
        login_states.append((self._keeper_params, self._keeper_login_attempted))
        param = params[len(login_states) - 1]
        self._keeper_params = param
        self._keeper_login_attempted = True
        return param

    class _FakeCmd:
        def execute(self, params, **kwargs):
            seen_params.append(params)
            assert kwargs["project_name"] == "customer-prod"
            assert kwargs["file_name"] == "/tmp/manifest.json"
            if len(seen_params) == 1:
                raise KeeperApiError("session_token_expired", "Session token expired")
            print("import ok")

    monkeypatch.setattr(CommanderCliProvider, "_get_keeper_params", fake_get_params)
    monkeypatch.setitem(
        sys.modules,
        "keepercommander.commands.pam_import.edit",
        types.SimpleNamespace(PAMProjectImportCommand=_FakeCmd),
    )

    provider = CommanderCliProvider(folder_uid="folder-uid")

    output = provider._run_cmd(
        [
            "pam",
            "project",
            "import",
            "--file",
            "/tmp/manifest.json",
            "--name",
            "customer-prod",
        ]
    )

    assert output.strip() == "import ok"
    assert seen_params == params
    assert login_states == [(None, False), (None, False)]


def test_run_cmd_retries_session_expiry_once_then_preserves_failure_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from keepercommander.error import KeeperApiError

    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    params = [object(), object()]
    login_states: list[tuple[object | None, bool]] = []
    seen_params: list[object] = []

    def fake_get_params(self: CommanderCliProvider) -> object:
        login_states.append((self._keeper_params, self._keeper_login_attempted))
        param = params[len(login_states) - 1]
        self._keeper_params = param
        self._keeper_login_attempted = True
        return param

    class _FakeCmd:
        def execute(self, params, **kwargs):
            seen_params.append(params)
            attempt = len(seen_params)
            print(f"stdout attempt {attempt}")
            print(f"stderr attempt {attempt}", file=sys.stderr)
            raise KeeperApiError("session_token_expired", "Session token expired")

    monkeypatch.setattr(CommanderCliProvider, "_get_keeper_params", fake_get_params)
    monkeypatch.setitem(
        sys.modules,
        "keepercommander.commands.pam_import.edit",
        types.SimpleNamespace(PAMProjectImportCommand=_FakeCmd),
    )

    provider = CommanderCliProvider(folder_uid="folder-uid")

    with pytest.raises(CapabilityError) as exc_info:
        provider._run_cmd(
            [
                "pam",
                "project",
                "import",
                "--file",
                "/tmp/manifest.json",
                "--name",
                "customer-prod",
            ]
        )

    assert "in-process keeper pam project import failed" in exc_info.value.reason
    assert "KeeperApiError" in exc_info.value.reason
    assert "session" in exc_info.value.reason.casefold()
    assert seen_params == params
    assert login_states == [(None, False), (None, False)]
    assert "stdout attempt 2" in exc_info.value.context["stdout"]
    assert "stderr attempt 2" in exc_info.value.context["stderr"]


def test_run_cmd_does_not_retry_non_session_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    params = [object()]
    seen_params: list[object] = []

    def fake_get_params(self: CommanderCliProvider) -> object:
        self._keeper_params = params[0]
        self._keeper_login_attempted = True
        return params[0]

    class _FakeCmd:
        def execute(self, params, **kwargs):
            seen_params.append(params)
            print("stdout before non-session failure")
            print("stderr before non-session failure", file=sys.stderr)
            raise RuntimeError("non-session failure")

    monkeypatch.setattr(CommanderCliProvider, "_get_keeper_params", fake_get_params)
    monkeypatch.setitem(
        sys.modules,
        "keepercommander.commands.pam_import.edit",
        types.SimpleNamespace(PAMProjectImportCommand=_FakeCmd),
    )

    provider = CommanderCliProvider(folder_uid="folder-uid")

    with pytest.raises(CapabilityError) as exc_info:
        provider._run_cmd(
            [
                "pam",
                "project",
                "import",
                "--file",
                "/tmp/manifest.json",
                "--name",
                "customer-prod",
            ]
        )

    assert "RuntimeError: non-session failure" in exc_info.value.reason
    assert seen_params == params
    assert "stdout before non-session failure" in exc_info.value.context["stdout"]
    assert "stderr before non-session failure" in exc_info.value.context["stderr"]


def test_write_marker_refreshes_session_once_on_message_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import keepercommander

    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    params = [object(), object()]
    login_states: list[tuple[object | None, bool]] = []

    def fake_get_params(self: CommanderCliProvider) -> object:
        login_states.append((self._keeper_params, self._keeper_login_attempted))
        param = params[len(login_states) - 1]
        self._keeper_params = param
        self._keeper_login_attempted = True
        return param

    class _FakeTypedRecord:
        def __init__(self) -> None:
            self.custom: list[object] = []

    class _FakeKeeperRecord:
        @staticmethod
        def load(params, keeper_uid):
            loads.append((params, keeper_uid))
            return _FakeTypedRecord()

    class _FakeTypedField:
        @staticmethod
        def new_field(field_type, value, label):
            return types.SimpleNamespace(type=field_type, value=[value], label=label)

    syncs: list[object] = []
    loads: list[tuple[object, str]] = []
    updates: list[tuple[object, _FakeTypedRecord]] = []

    fake_api = types.SimpleNamespace()

    def fake_sync_down(params) -> None:
        syncs.append(params)
        if len(syncs) == 1:
            raise RuntimeError("session token expired")

    fake_api.sync_down = fake_sync_down
    fake_record_management = types.SimpleNamespace(
        update_record=lambda params, record: updates.append((params, record))
    )
    fake_vault = types.SimpleNamespace(
        KeeperRecord=_FakeKeeperRecord,
        TypedField=_FakeTypedField,
        TypedRecord=_FakeTypedRecord,
    )

    monkeypatch.setattr(CommanderCliProvider, "_get_keeper_params", fake_get_params)
    monkeypatch.setattr(keepercommander, "api", fake_api, raising=False)
    monkeypatch.setattr(keepercommander, "record_management", fake_record_management, raising=False)
    monkeypatch.setattr(keepercommander, "vault", fake_vault, raising=False)
    monkeypatch.setitem(sys.modules, "keepercommander.api", fake_api)
    monkeypatch.setitem(sys.modules, "keepercommander.record_management", fake_record_management)
    monkeypatch.setitem(sys.modules, "keepercommander.vault", fake_vault)

    provider = CommanderCliProvider(folder_uid="folder-uid")
    marker = encode_marker(
        uid_ref="prod-db",
        manifest="customer-prod",
        resource_type="pamDatabase",
        last_applied_at="2026-04-24T12:34:56Z",
    )

    provider._write_marker("keeper-created-uid", marker)

    assert login_states == [(None, False), (None, False)]
    assert syncs == [params[0], params[1], params[1]]
    assert loads == [(params[1], "keeper-created-uid")]
    assert len(updates) == 1
    assert updates[0][0] is params[1]
    assert updates[0][1].custom[0].label == "keeper_declarative_manager"
    assert updates[0][1].custom[0].value == [serialize_marker(marker)]


def test_apply_reference_existing_splits_to_extend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.utc_timestamp", lambda: "2026-04-24T12:34:56Z"
    )

    calls: list[list[str]] = []

    def recorder(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        if args == ["ls", "--format", "json", "PAM Environments"]:
            raise CapabilityError(reason="missing")
        if args == ["mkdir", "-uf", "PAM Environments"]:
            return ""
        if args == ["ls", "--format", "json", "PAM Environments/customer-prod"]:
            if ["mkdir", "-uf", "PAM Environments/customer-prod"] not in calls:
                raise CapabilityError(reason="missing")
            return json.dumps(
                [
                    {
                        "type": "folder",
                        "uid": "resources-folder",
                        "name": "customer-prod - Resources",
                    },
                    {"type": "folder", "uid": "users-folder", "name": "customer-prod - Users"},
                ]
            )
        if args == ["mkdir", "-uf", "PAM Environments/customer-prod"]:
            return ""
        if args == [
            "ls",
            "--format",
            "json",
            "PAM Environments/customer-prod/customer-prod - Resources",
        ]:
            if not any(
                call[:6]
                == [
                    "mkdir",
                    "-sf",
                    "--manage-users",
                    "--manage-records",
                    "--can-edit",
                    "--can-share",
                ]
                and call[-1] == "PAM Environments/customer-prod/customer-prod - Resources"
                for call in calls
            ):
                raise CapabilityError(reason="missing")
            return json.dumps([])
        if args == [
            "ls",
            "--format",
            "json",
            "PAM Environments/customer-prod/customer-prod - Users",
        ]:
            if not any(
                call[:6]
                == [
                    "mkdir",
                    "-sf",
                    "--manage-users",
                    "--manage-records",
                    "--can-edit",
                    "--can-share",
                ]
                and call[-1] == "PAM Environments/customer-prod/customer-prod - Users"
                for call in calls
            ):
                raise CapabilityError(reason="missing")
            return json.dumps([])
        if args[:6] == [
            "mkdir",
            "-sf",
            "--manage-users",
            "--manage-records",
            "--can-edit",
            "--can-share",
        ]:
            return ""
        if args[:4] == ["secrets-manager", "share", "add", "--app"]:
            return ""
        if args == ["pam", "gateway", "list", "--format", "json"]:
            return json.dumps(
                {
                    "gateways": [
                        {
                            "ksm_app_name": "Lab GW Application",
                            "ksm_app_uid": "app-uid",
                            "ksm_app_accessible": True,
                            "gateway_name": "Lab GW Rocky",
                            "gateway_uid": "gw-uid",
                            "status": "ONLINE",
                            "gateway_version": "1.7.6",
                        }
                    ]
                }
            )
        if args == ["pam", "config", "list", "--format", "json"]:
            return json.dumps(
                {
                    "configurations": [
                        {
                            "uid": "cfg-uid",
                            "config_name": "LW Gateway Configuration",
                            "config_type": "pamNetworkConfiguration",
                            "shared_folder": {
                                "name": "Lab GW Folder - Resources",
                                "uid": "folder-uid",
                            },
                            "gateway_uid": "gw-uid",
                            "resource_record_uids": [],
                        }
                    ]
                }
            )
        if args[:4] == ["pam", "project", "extend", "--config"]:
            payload = json.loads(Path(args[6]).read_text(encoding="utf-8"))
            assert payload == {
                "pam_data": {
                    "resources": [
                        {
                            "type": "pamMachine",
                            "title": "db-prod",
                            "folder_path": "customer-prod - Resources",
                        }
                    ]
                }
            }
            return ""
        if args == ["ls", "resources-folder", "--format", "json"]:
            return json.dumps(
                [
                    {
                        "type": "record",
                        "uid": "keeper-created-uid",
                        "name": "db-prod",
                        "details": "Type: pamMachine, Description: ...",
                    }
                ]
            )
        if args == ["ls", "users-folder", "--format", "json"]:
            return json.dumps([])
        if args == ["get", "keeper-created-uid", "--format", "json"]:
            return json.dumps(
                {
                    "record_uid": "keeper-created-uid",
                    "title": "db-prod",
                    "type": "pamMachine",
                    "fields": [],
                    "custom": [],
                }
            )
        if args[:2] == ["record-update", "--record"]:
            return ""
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", recorder)
    _install_fake_write_marker(monkeypatch, calls)
    provider = CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source={
            "version": "1",
            "name": "customer-prod",
            "gateways": [{"uid_ref": "gw", "name": "Lab GW Rocky", "mode": "reference_existing"}],
            "pam_configurations": [
                {
                    "uid_ref": "cfg",
                    "title": "Lab Rocky PAM Configuration",
                    "environment": "local",
                    "gateway_uid_ref": "gw",
                }
            ],
            "resources": [{"uid_ref": "prod-db", "type": "pamMachine", "title": "db-prod"}],
        },
    )
    plan = Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="cfg",
                resource_type="pam_configuration",
                title="Lab Rocky PAM Configuration",
                after={"title": "Lab Rocky PAM Configuration"},
            ),
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="prod-db",
                resource_type="pamMachine",
                title="db-prod",
                after={"title": "db-prod"},
            ),
        ],
        order=["cfg", "prod-db"],
    )

    outcomes = provider.apply_plan(plan)

    assert any(call[:4] == ["pam", "project", "extend", "--config"] for call in calls)
    assert provider.last_resolved_folder_uid == "resources-folder"
    assert outcomes[0].details["reused_existing"] is True
    assert outcomes[0].details["marker_written"] is True
    assert outcomes[1].details["marker_written"] is True


def test_apply_rejects_keepercommander_below_minimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DOR / SDK_DA Phase 4 — Commander Python module must meet the documented floor."""
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli._keepercommander_installed_tuple",
        lambda: (17, 2, 12),
    )
    provider = CommanderCliProvider(folder_uid="folder-uid")
    plan = Plan(manifest_name="empty", changes=[], order=[])

    with pytest.raises(CapabilityError, match="below the minimum"):
        provider.apply_plan(plan)


def test_apply_partial_failure_records_outcomes_then_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mid-batch CapabilityError leaves prior create outcomes inspectable on the exception."""
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.utc_timestamp", lambda: "2026-04-26T00:00:00Z"
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _apply_recorder(
            calls,
            project_name="dor-partial",
            discovered_entries=[
                {
                    "type": "record",
                    "uid": "uid-a",
                    "name": "db-a",
                    "details": "Type: pamDatabase, Description: ...",
                },
                {
                    "type": "record",
                    "uid": "uid-b",
                    "name": "db-b",
                    "details": "Type: pamDatabase, Description: ...",
                },
            ],
            get_payloads={
                "uid-a": {
                    "record_uid": "uid-a",
                    "title": "db-a",
                    "type": "pamDatabase",
                    "fields": [],
                    "custom": [],
                },
                "uid-b": {
                    "record_uid": "uid-b",
                    "title": "db-b",
                    "type": "pamDatabase",
                    "fields": [],
                    "custom": [],
                },
            },
            monkeypatch=None,
        ),
    )
    marker_calls = {"count": 0}

    def fail_second_marker(self: CommanderCliProvider, keeper_uid: str, marker: dict) -> None:
        marker_calls["count"] += 1
        if marker_calls["count"] == 2:
            raise CapabilityError(
                reason="simulated marker write failure",
                next_action="retry after fixing the vault session",
            )

    monkeypatch.setattr(CommanderCliProvider, "_write_marker", fail_second_marker)

    provider = CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source={
            "version": "1",
            "name": "dor-partial",
            "resources": [
                {"uid_ref": "prod-a", "type": "pamDatabase", "title": "db-a"},
                {"uid_ref": "prod-b", "type": "pamDatabase", "title": "db-b"},
            ],
        },
    )
    plan = Plan(
        manifest_name="dor-partial",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="prod-a",
                resource_type="pamDatabase",
                title="db-a",
                after={"title": "db-a"},
            ),
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="prod-b",
                resource_type="pamDatabase",
                title="db-b",
                after={"title": "db-b"},
            ),
        ],
        order=["prod-a", "prod-b"],
    )

    with pytest.raises(CapabilityError) as exc_info:
        provider.apply_plan(plan)

    partial = exc_info.value.context.get("partial_outcomes")
    assert partial is not None
    assert len(partial) == 2
    assert partial[0].details["marker_written"] is True
    assert partial[0].details["verified"] is True
    assert partial[1].details["apply_failed"] is True
    assert "simulated marker write failure" in partial[1].details["apply_failure_reason"]
    assert marker_calls["count"] == 2


def test_vault_discover_keeps_login_records_only(monkeypatch: pytest.MonkeyPatch) -> None:
    ls_payload = [
        {"type": "record", "uid": "u-login", "details": "Type: login"},
        {"type": "record", "uid": "u-host", "details": "Type: pamMachine"},
    ]
    get_payloads = {
        "u-login": {"type": "login", "title": "L", "record_uid": "u-login", "fields": []},
        "u-host": {"type": "pamMachine", "title": "H", "record_uid": "u-host", "fields": []},
    }
    provider = _discover_provider(monkeypatch, ls_payload=ls_payload, get_payloads=get_payloads)
    provider._manifest_source = {"schema": "keeper-vault.v1", "records": []}
    rows = provider.discover()
    assert [r.keeper_uid for r in rows] == ["u-login"]


def test_vault_apply_plan_create_writes_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    from keeper_sdk.providers import commander_cli as commander_cli_mod

    monkeypatch.setattr(
        commander_cli_mod, "_ensure_keepercommander_version_for_apply", lambda: None
    )
    monkeypatch.setattr(
        commander_cli_mod.CommanderCliProvider,
        "_vault_add_login_record",
        lambda self, after: "NEWUID",
    )
    marker_calls: list[dict[str, str | None]] = []

    def fake_write_marker(self, keeper_uid: str, marker: dict) -> None:
        marker_calls.append({"keeper_uid": keeper_uid, "uid_ref": marker.get("uid_ref")})

    monkeypatch.setattr(
        commander_cli_mod.CommanderCliProvider, "_write_marker", fake_write_marker
    )
    monkeypatch.setattr(
        commander_cli_mod.CommanderCliProvider, "_run_cmd", lambda self, args: ""
    )
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    provider = commander_cli_mod.CommanderCliProvider(
        folder_uid="fld",
        manifest_source={"schema": "keeper-vault.v1", "records": []},
    )
    plan = Plan(
        manifest_name="demo",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="r1",
                resource_type="login",
                title="T1",
                after={"type": "login", "title": "T1", "fields": []},
            )
        ],
        order=["r1"],
    )
    outcomes = provider.apply_plan(plan)
    assert outcomes[0].keeper_uid == "NEWUID"
    assert marker_calls == [{"keeper_uid": "NEWUID", "uid_ref": "r1"}]


def test_vault_patch_login_record_data_skips_ignored_and_sets_title() -> None:
    existing = {"type": "login", "title": "Old", "fields": [], "custom": []}
    patch = {"uid_ref": "x", "title": "New", "notes": "n1"}
    out = CommanderCliProvider._vault_patch_login_record_data(existing, patch)
    assert out["title"] == "New"
    assert out["notes"] == "n1"
    assert out["type"] == "login"


def test_vault_patch_login_record_data_replaces_fields_array() -> None:
    existing = {
        "type": "login",
        "title": "T",
        "fields": [{"type": "login", "label": "login", "value": ["u1"]}],
        "custom": [],
    }
    patch = {"fields": [{"type": "login", "label": "login", "value": ["u2"]}]}
    out = CommanderCliProvider._vault_patch_login_record_data(existing, patch)
    assert out["fields"][0]["value"] == ["u2"]


def test_vault_merge_custom_preserves_marker() -> None:
    existing = [{"label": MARKER_FIELD_LABEL, "type": "text", "value": ["{}"]}]
    patch = [{"label": "other", "type": "text", "value": ["x"]}]
    out = CommanderCliProvider._vault_merge_custom_for_update(existing, patch)
    labels = {e.get("label") for e in out}
    assert MARKER_FIELD_LABEL in labels
    assert "other" in labels


def test_vault_apply_plan_update_body_then_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    from keeper_sdk.providers import commander_cli as commander_cli_mod

    monkeypatch.setattr(
        commander_cli_mod, "_ensure_keepercommander_version_for_apply", lambda: None
    )
    body_calls: list[tuple[str, dict[str, str]]] = []

    def fake_body(self, keeper_uid: str, patch: dict[str, str]) -> None:
        body_calls.append((keeper_uid, dict(patch)))

    monkeypatch.setattr(
        commander_cli_mod.CommanderCliProvider, "_vault_apply_login_body_update", fake_body
    )
    marker_calls: list[dict[str, str | None]] = []

    def fake_write_marker(self, keeper_uid: str, marker: dict) -> None:
        marker_calls.append({"keeper_uid": keeper_uid, "uid_ref": marker.get("uid_ref")})

    monkeypatch.setattr(
        commander_cli_mod.CommanderCliProvider, "_write_marker", fake_write_marker
    )
    monkeypatch.setattr(
        commander_cli_mod.CommanderCliProvider, "_run_cmd", lambda self, args: ""
    )
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )

    provider = commander_cli_mod.CommanderCliProvider(
        folder_uid="fld",
        manifest_source={"schema": "keeper-vault.v1", "records": []},
    )
    plan = Plan(
        manifest_name="demo",
        changes=[
            Change(
                kind=ChangeKind.UPDATE,
                uid_ref="r1",
                resource_type="login",
                title="T1",
                keeper_uid="UID1",
                after={"title": "T1-renamed"},
            )
        ],
        order=["r1"],
    )
    outcomes = provider.apply_plan(plan)
    assert body_calls == [("UID1", {"title": "T1-renamed"})]
    assert marker_calls == [{"keeper_uid": "UID1", "uid_ref": "r1"}]
    assert outcomes[0].details.get("record_updated") is True
    assert outcomes[0].details.get("marker_written") is True
