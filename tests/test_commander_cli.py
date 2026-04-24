"""Tests for the Commander CLI provider export parsing."""

from __future__ import annotations

import json

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


def _sample_payload() -> dict[str, object]:
    return {
        "resources": [
            {
                "record_uid": "res-1",
                "title": "db-prod",
                "type": "pamDatabase",
                "custom_fields": {
                    "keeper_declarative_manager": serialize_marker(
                        encode_marker(
                            uid_ref="db-prod",
                            manifest="prod",
                            resource_type="pamDatabase",
                        )
                    )
                },
            }
        ],
        "users": [
            {
                "uid": "user-1",
                "record_title": "svc-admin",
                "custom": [
                    {
                        "label": "keeper_declarative_manager",
                        "value": serialize_marker(
                            encode_marker(
                                uid_ref="svc-admin",
                                manifest="prod",
                                resource_type="pamUser",
                            )
                        ),
                    }
                ],
            },
            {
                "uid": "login-1",
                "name": "ssh-login",
                "type": "login",
            },
        ],
        "pam_configurations": [
            {
                "keeper_uid": "cfg-1",
                "title": "default config",
            }
        ],
        "gateways": [
            {
                "record_uid": "gw-1",
                "title": "gw-lon-1",
            }
        ],
    }


def test_discover_requires_folder_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")
    provider = CommanderCliProvider(folder_uid=None)

    with pytest.raises(CapabilityError) as exc_info:
        provider.discover()

    assert "requires folder_uid" in exc_info.value.reason
    assert exc_info.value.next_action == "set --folder-uid on the CLI or KEEPER_DECLARATIVE_FOLDER env var"


def test_discover_parses_export_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch, json.dumps(_sample_payload()))

    records = provider.discover()

    assert [(record.keeper_uid, record.title, record.resource_type) for record in records] == [
        ("res-1", "db-prod", "pamDatabase"),
        ("user-1", "svc-admin", "pamUser"),
        ("login-1", "ssh-login", "login"),
        ("cfg-1", "default config", "pam_configuration"),
        ("gw-1", "gw-lon-1", "gateway"),
    ]
    assert records[0].marker is not None
    assert records[0].marker["uid_ref"] == "db-prod"
    assert records[1].marker is not None
    assert records[1].marker["uid_ref"] == "svc-admin"
    assert records[1].payload["_legacy_type_fallback"] is True
    assert records[2].payload.get("_legacy_type_fallback") is None


def test_discover_unwraps_project_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch, json.dumps({"project": _sample_payload()}))

    records = provider.discover()

    assert [(record.keeper_uid, record.title, record.resource_type) for record in records] == [
        ("res-1", "db-prod", "pamDatabase"),
        ("user-1", "svc-admin", "pamUser"),
        ("login-1", "ssh-login", "login"),
        ("cfg-1", "default config", "pam_configuration"),
        ("gw-1", "gw-lon-1", "gateway"),
    ]


def test_discover_raises_on_empty_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch, "")

    with pytest.raises(CapabilityError) as exc_info:
        provider.discover()

    assert exc_info.value.reason == "keeper pam project export produced no output"


def test_apply_writes_marker_after_create(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")
    monkeypatch.setattr("keeper_sdk.providers.commander_cli._utc_now", lambda: "2026-04-24T12:34:56Z")

    calls: list[list[str]] = []

    def recorder(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        if args[:3] == ["pam", "project", "import"]:
            return ""
        if args[:3] == ["pam", "project", "export"]:
            return json.dumps(
                {
                    "resources": [
                        {
                            "record_uid": "keeper-created-uid",
                            "title": "db-prod",
                            "type": "pamDatabase",
                        }
                    ]
                }
            )
        if args[:2] == ["record-update", "--record"]:
            return ""
        raise AssertionError(f"unexpected command: {args}")

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

    outcomes = provider.apply_plan(plan)

    assert [call[:3] for call in calls] == [
        ["pam", "project", "import"],
        ["pam", "project", "export"],
        ["record-update", "--record", "keeper-created-uid"],
    ]
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
    assert all(call[:3] != ["pam", "project", "export"] for call in calls)


def test_apply_skips_marker_when_record_not_discoverable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")

    calls: list[list[str]] = []

    def recorder(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        if args[:3] == ["pam", "project", "import"]:
            return ""
        if args[:3] == ["pam", "project", "export"]:
            return json.dumps({"resources": []})
        raise AssertionError(f"unexpected command: {args}")

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

    outcomes = provider.apply_plan(plan)

    assert outcomes[0].details["marker_written"] is False
    assert outcomes[0].details["reason"] == "record not found after apply"
    assert all(call[0] != "record-update" for call in calls)


def test_apply_verifies_fields_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")
    monkeypatch.setattr("keeper_sdk.providers.commander_cli._utc_now", lambda: "2026-04-24T12:34:56Z")

    calls: list[list[str]] = []

    def recorder(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        if args[:3] == ["pam", "project", "import"]:
            return ""
        if args[:3] == ["pam", "project", "export"]:
            return json.dumps(
                {
                    "resources": [
                        {
                            "record_uid": "keeper-created-uid",
                            "title": "db-prod",
                            "type": "pamDatabase",
                            "host": "db.example.com",
                            "port": 5432,
                        }
                    ]
                }
            )
        if args[:2] == ["record-update", "--record"]:
            return ""
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", recorder)
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

    assert [call[:3] for call in calls] == [
        ["pam", "project", "import"],
        ["pam", "project", "export"],
        ["record-update", "--record", "keeper-created-uid"],
    ]
    assert outcomes[0].details["marker_written"] is True
    assert outcomes[0].details["verified"] is True
    assert "field_drift" not in outcomes[0].details


def test_apply_reports_field_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper")
    monkeypatch.setattr("keeper_sdk.providers.commander_cli._utc_now", lambda: "2026-04-24T12:34:56Z")

    calls: list[list[str]] = []

    def recorder(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        if args[:3] == ["pam", "project", "import"]:
            return ""
        if args[:3] == ["pam", "project", "export"]:
            return json.dumps(
                {
                    "resources": [
                        {
                            "record_uid": "keeper-created-uid",
                            "title": "db-prod",
                            "type": "pamDatabase",
                            "host": "db-observed.example.com",
                            "port": 5432,
                        }
                    ]
                }
            )
        if args[:2] == ["record-update", "--record"]:
            return ""
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", recorder)
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
