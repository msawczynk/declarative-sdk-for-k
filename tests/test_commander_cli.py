"""Tests for the Commander CLI provider discovery and apply flows."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.metadata import encode_marker, serialize_marker
from keeper_sdk.core.planner import Plan
from keeper_sdk.providers.commander_cli import (
    CommanderCliProvider,
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
        key = tuple(args)
        if key in command_map:
            payload = command_map[key]
            return json.dumps(payload) if not isinstance(payload, str) else payload
        if args[:1] == ["get"]:
            payload = get_payload
            if payload is None:
                raise AssertionError(f"unexpected get uid {args[1]}")
            return json.dumps(payload) if not isinstance(payload, str) else payload
        if args[:2] == ["record-update", "--record"]:
            return ""
        if args[:3] == ["rm", "--force", "DEL_UID"]:
            return ""
        raise AssertionError(f"unexpected command: {args}")

    return recorder


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
