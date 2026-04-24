"""Tests for the Commander CLI provider export parsing."""

from __future__ import annotations

import json

import pytest

from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.metadata import encode_marker, serialize_marker
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
