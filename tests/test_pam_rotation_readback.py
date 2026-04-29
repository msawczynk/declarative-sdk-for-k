"""Offline tests for Commander PAM rotation readback wiring."""

from __future__ import annotations

import json

import pytest

from keeper_sdk.core.metadata import encode_marker, serialize_marker
from keeper_sdk.providers.commander_cli import CommanderCliProvider


def _marker(uid_ref: str) -> dict[str, object]:
    return {
        "type": "text",
        "label": "keeper_declarative_manager",
        "value": [
            serialize_marker(
                encode_marker(
                    uid_ref=uid_ref,
                    manifest="customer-prod",
                    resource_type="pamUser",
                )
            )
        ],
    }


def _manifest() -> dict[str, object]:
    return {
        "version": "1",
        "name": "customer-prod",
        "resources": [
            {
                "uid_ref": "res.db",
                "type": "pamDatabase",
                "title": "db-prod",
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
                        },
                    },
                    {"uid_ref": "usr.admin", "type": "pamUser", "title": "admin-user"},
                ],
            }
        ],
    }


def test_get_pam_rotation_state_calls_record_uid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    calls: list[list[str]] = []

    def fake_run(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        return json.dumps(
            [
                {
                    "record_uid": "USER_UID",
                    "rotation_profile": "general",
                    "enabled": True,
                    "schedule": {"type": "CRON", "cron": "30 18 * * *"},
                    "password_complexity": "32,5,5,5,5",
                }
            ]
        )

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", fake_run)
    provider = CommanderCliProvider(folder_uid="folder-uid")

    assert provider._get_pam_rotation_state("USER_UID") == {
        "rotation": "general",
        "enabled": "on",
        "schedule": {"type": "CRON", "cron": "30 18 * * *"},
        "password_complexity": "32,5,5,5,5",
    }
    assert calls == [["pam", "rotation", "list", "--record-uid", "USER_UID", "--format", "json"]]


def test_discover_populates_rotation_settings_on_nested_pam_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    calls: list[list[str]] = []

    def fake_run(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        if args == ["ls", "folder-uid", "--format", "json"]:
            return json.dumps(
                [
                    {
                        "type": "record",
                        "uid": "USER_UID",
                        "name": "db-user",
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
        if args == ["get", "USER_UID", "--format", "json"]:
            return json.dumps(
                {
                    "record_uid": "USER_UID",
                    "title": "db-user",
                    "type": "pamUser",
                    "fields": [],
                    "custom": [_marker("usr.db")],
                }
            )
        if args == ["get", "ADMIN_UID", "--format", "json"]:
            return json.dumps(
                {
                    "record_uid": "ADMIN_UID",
                    "title": "admin-user",
                    "type": "pamUser",
                    "fields": [],
                    "custom": [_marker("usr.admin")],
                }
            )
        if args == ["pam", "rotation", "list", "--record-uid", "USER_UID", "--format", "json"]:
            return json.dumps(
                {
                    "rotations": [
                        {
                            "recordUid": "USER_UID",
                            "rotationSettings": {
                                "rotation": "general",
                                "enabled": "on",
                                "schedule": {"type": "CRON", "cron": "30 18 * * *"},
                                "passwordComplexity": "32,5,5,5,5",
                            },
                        }
                    ]
                }
            )
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", fake_run)
    provider = CommanderCliProvider(folder_uid="folder-uid", manifest_source=_manifest())
    provider._manifest_name = None

    records = provider.discover()

    by_uid = {record.keeper_uid: record for record in records}
    assert by_uid["USER_UID"].payload["rotation_settings"] == {
        "rotation": "general",
        "enabled": "on",
        "schedule": {"type": "CRON", "cron": "30 18 * * *"},
        "password_complexity": "32,5,5,5,5",
    }
    assert "rotation_settings" not in by_uid["ADMIN_UID"].payload
    assert [
        "pam",
        "rotation",
        "list",
        "--record-uid",
        "USER_UID",
        "--format",
        "json",
    ] in calls
