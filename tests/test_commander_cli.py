"""Tests for the Commander CLI provider discovery and apply flows."""

from __future__ import annotations

import json
import subprocess

import pytest

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.metadata import encode_marker, serialize_marker
from keeper_sdk.core.planner import Plan
from keeper_sdk.providers.commander_cli import CommanderCliProvider


def _provider(monkeypatch: pytest.MonkeyPatch, stdout: str = "") -> CommanderCliProvider:
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")
    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", lambda self, args: stdout)
    return CommanderCliProvider(folder_uid="folder-uid")


def _discover_provider(
    monkeypatch: pytest.MonkeyPatch,
    *,
    ls_payload: object,
    get_payloads: dict[str, object] | None = None,
) -> CommanderCliProvider:
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")

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
            {"type": "folder", "uid": "pam-env-root", "name": "PAM Environments"}
        ],
        ("ls", "--format", "json", "pam-env-root"): [
            {"type": "folder", "uid": "project-folder", "name": project_name}
        ],
        ("ls", "--format", "json", "project-folder"): [
            {"type": "folder", "uid": "resources-folder", "name": f"{project_name} - Resources"}
        ],
    }


def _apply_recorder(
    calls: list[list[str]],
    *,
    project_name: str = "customer-prod",
    discovered_entries: object | None = None,
    get_payload: object | None = None,
):
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
        if args[:2] == ["rm", "DEL_UID"]:
            return ""
        raise AssertionError(f"unexpected command: {args}")

    return recorder


def test_discover_requires_folder_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")
    provider = CommanderCliProvider(folder_uid=None)

    with pytest.raises(CapabilityError) as exc_info:
        provider.discover()

    assert "run apply_plan() first" in exc_info.value.reason
    assert exc_info.value.next_action == "pass --folder-uid (or KEEPER_DECLARATIVE_FOLDER), or call apply_plan() first"


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
                "custom": [{"type": "text", "label": "keeper_declarative_manager", "value": [marker]}],
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
            {"type": "record", "uid": "R1", "name": "host1", "details": "Type: pamMachine, Description: ..."},
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
            {"type": "record", "uid": "R1", "name": "svc-admin", "details": "Type: pamUser, Description: ..."}
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


def test_resolve_project_resources_folder_walks_pam_environments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")

    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _apply_recorder(calls, project_name="customer-prod", discovered_entries=[]),
    )
    provider = CommanderCliProvider(folder_uid=None)

    resolved = provider._resolve_project_resources_folder("customer-prod")

    assert resolved == "resources-folder"
    assert provider.last_resolved_folder_uid == "resources-folder"
    assert calls == [
        ["ls", "--format", "json", "PAM Environments"],
        ["ls", "--format", "json", "pam-env-root"],
        ["ls", "--format", "json", "project-folder"],
    ]


def test_apply_writes_marker_after_create(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")
    monkeypatch.setattr("keeper_sdk.providers.commander_cli._utc_now", lambda: "2026-04-24T12:34:56Z")

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

    assert calls[:6] == [
        ["pam", "project", "import", "--file", calls[0][4], "--name", "customer-prod"],
        ["ls", "--format", "json", "PAM Environments"],
        ["ls", "--format", "json", "pam-env-root"],
        ["ls", "--format", "json", "project-folder"],
        ["ls", "resources-folder", "--format", "json"],
        ["get", "keeper-created-uid", "--format", "json"],
    ]
    assert calls[6][:3] == ["record-update", "--record", "keeper-created-uid"]
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
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")

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
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")

    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        _apply_recorder(calls, project_name="customer-prod", discovered_entries=[]),
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
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")
    monkeypatch.setattr("keeper_sdk.providers.commander_cli._utc_now", lambda: "2026-04-24T12:34:56Z")

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
                "fields": [{"type": "host", "value": [{"hostName": "db.example.com", "port": 5432}]}],
                "custom": [],
            },
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

    assert calls[:6] == [
        ["pam", "project", "import", "--file", calls[0][4], "--name", "customer-prod"],
        ["ls", "--format", "json", "PAM Environments"],
        ["ls", "--format", "json", "pam-env-root"],
        ["ls", "--format", "json", "project-folder"],
        ["ls", "resources-folder", "--format", "json"],
        ["get", "keeper-created-uid", "--format", "json"],
    ]
    assert calls[6][:3] == ["record-update", "--record", "keeper-created-uid"]
    assert outcomes[0].details["marker_written"] is True
    assert outcomes[0].details["verified"] is True
    assert "field_drift" not in outcomes[0].details


def test_apply_reports_field_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")
    monkeypatch.setattr("keeper_sdk.providers.commander_cli._utc_now", lambda: "2026-04-24T12:34:56Z")

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
                    {"type": "host", "value": [{"hostName": "db-observed.example.com", "port": 5432}]}
                ],
                "custom": [],
            },
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
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")
    monkeypatch.setattr("keeper_sdk.providers.commander_cli._utc_now", lambda: "2026-04-24T12:34:56Z")

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

    rm_index = calls.index(["rm", "DEL_UID"])
    import_index = next(idx for idx, call in enumerate(calls) if call[:3] == ["pam", "project", "import"])
    assert rm_index > import_index
    assert calls[-1] == ["rm", "DEL_UID"]
    delete_outcome = next(outcome for outcome in outcomes if outcome.action == "delete")
    assert delete_outcome.keeper_uid == "DEL_UID"
    assert delete_outcome.details["keeper_uid"] == "DEL_UID"
    assert delete_outcome.details["removed"] is True


def test_apply_dry_run_delete_does_not_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")

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
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")

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


def test_run_cmd_raises_on_rc0_pam_import_silent_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="",
            stderr='Project name is required - JSON property: "project": "Project 1"',
        )

    monkeypatch.setattr("keeper_sdk.providers.commander_cli.subprocess.run", fake_run)
    provider = CommanderCliProvider(folder_uid="folder-uid")

    with pytest.raises(CapabilityError) as exc_info:
        provider._run_cmd(["pam", "project", "import", "--file", "/tmp/manifest.json"])

    assert "silent-fail" in exc_info.value.reason
    assert "Project name is required" in exc_info.value.reason
