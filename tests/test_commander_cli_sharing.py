"""Offline tests for Commander CLI sharing helper argv construction."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.providers.commander_cli import CommanderCliProvider


def _provider(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stdout: str = "",
) -> tuple[CommanderCliProvider, list[list[str]]]:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    calls: list[list[str]] = []

    def recorder(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        return stdout

    def ensure_folder(self: CommanderCliProvider, path: str) -> None:
        calls.append(["ensure-folder", path])

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", recorder)
    monkeypatch.setattr(CommanderCliProvider, "_ensure_folder_exists", ensure_folder)
    monkeypatch.setattr(
        CommanderCliProvider,
        "_resolve_folder_uid_by_path",
        lambda self, path: f"uid:{path}",
    )
    return CommanderCliProvider(folder_uid="folder-uid"), calls


def test_create_user_folder_uses_mkdir_user_folder_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, calls = _provider(monkeypatch)

    provider._create_user_folder(path="/Customers/Acme")

    assert calls == [["ensure-folder", "/Customers"], ["mkdir", "-uf", "/Customers/Acme"]]


def test_create_user_folder_includes_color(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, calls = _provider(monkeypatch)

    provider._create_user_folder(path="/Customers/Acme", parent_uid="ignored", color="green")

    assert calls == [
        ["ensure-folder", "/Customers"],
        ["mkdir", "-uf", "/Customers/Acme", "--color", "green"],
    ]


def test_create_user_folder_allows_root_level_path(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, calls = _provider(monkeypatch)

    provider._create_user_folder(path="/Customers")

    assert calls == [["mkdir", "-uf", "/Customers"]]


def test_create_shared_folder_defaults_to_all_default_permissions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, calls = _provider(monkeypatch)

    provider._create_shared_folder(path="/Customers/Acme Shared")

    assert calls == [
        ["ensure-folder", "/Customers"],
        [
            "mkdir",
            "-sf",
            "--manage-records",
            "--manage-users",
            "--can-edit",
            "--can-share",
            "/Customers/Acme Shared",
        ],
    ]


def test_create_shared_folder_omits_false_permission_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, calls = _provider(monkeypatch)

    provider._create_shared_folder(
        path="/Customers/Acme Shared",
        manage_records=False,
        manage_users=True,
        can_edit=False,
        can_share=True,
    )

    assert calls == [
        ["ensure-folder", "/Customers"],
        ["mkdir", "-sf", "--manage-users", "--can-share", "/Customers/Acme Shared"],
    ]


def test_folder_parent_path_handles_absolute_relative_and_escaped_slashes() -> None:
    assert CommanderCliProvider._folder_parent_path("/Customers/Acme/Login") == "/Customers/Acme"
    assert CommanderCliProvider._folder_parent_path("Customers/Acme") == "Customers"
    assert CommanderCliProvider._folder_parent_path("/Customers") is None
    assert CommanderCliProvider._folder_parent_path("Customer//Name/Acme") == "Customer//Name"


def test_move_folder_uses_selector_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, calls = _provider(monkeypatch)

    provider._move_folder(source="/Customers/Acme", destination="/Customers/Archive")
    provider._move_folder(
        source="/Customers/Acme Shared",
        destination="/Customers/Archive",
        is_shared=True,
    )

    assert calls == [
        ["mv", "--user-folder", "/Customers/Acme", "/Customers/Archive"],
        ["mv", "--shared-folder", "/Customers/Acme Shared", "/Customers/Archive"],
    ]


def test_delete_folder_uses_forced_rmdir(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, calls = _provider(monkeypatch)

    provider._delete_folder(path_or_uid="FOLDER_UID")

    assert calls == [["rmdir", "-f", "FOLDER_UID"]]


def test_share_record_to_user_grants_permissions_and_expiration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, calls = _provider(monkeypatch)

    provider._share_record_to_user(
        record_uid="REC_UID",
        user_email="user@example.com",
        can_edit=True,
        can_share=True,
        expiration_iso="2026-05-01 12:00:00",
    )

    assert calls == [
        [
            "share-record",
            "-a",
            "grant",
            "-e",
            "user@example.com",
            "-f",
            "-w",
            "-s",
            "--expire-at",
            "2026-05-01 12:00:00",
            "REC_UID",
        ]
    ]


def test_share_record_to_user_omits_false_permission_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, calls = _provider(monkeypatch)

    provider._share_record_to_user(
        record_uid="REC_UID",
        user_email="user@example.com",
        can_edit=False,
        can_share=False,
    )

    assert calls == [["share-record", "-a", "grant", "-e", "user@example.com", "-f", "REC_UID"]]


def test_revoke_record_share_from_user_uses_revoke_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, calls = _provider(monkeypatch)

    provider._revoke_record_share_from_user(record_uid="REC_UID", user_email="user@example.com")

    assert calls == [["share-record", "-a", "revoke", "-e", "user@example.com", "REC_UID"]]


def test_share_folder_to_user_grantee_sets_manage_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, calls = _provider(monkeypatch)

    provider._share_folder_to_grantee(
        shared_folder_uid="SF_UID",
        grantee_kind="user",
        identifier="user@example.com",
        manage_records=True,
        manage_users=False,
    )

    assert calls == [
        [
            "share-folder",
            "-a",
            "grant",
            "-e",
            "user@example.com",
            "-f",
            "-p",
            "on",
            "-o",
            "off",
            "SF_UID",
        ]
    ]


def test_share_folder_to_team_grantee_uses_email_parser_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, calls = _provider(monkeypatch)

    provider._share_folder_to_grantee(
        shared_folder_uid="SF_UID",
        grantee_kind="team",
        identifier="TEAM_UID",
        manage_records=False,
        manage_users=True,
    )

    assert calls == [
        [
            "share-folder",
            "-a",
            "grant",
            "-e",
            "TEAM_UID",
            "-f",
            "-p",
            "off",
            "-o",
            "on",
            "SF_UID",
        ]
    ]


def test_share_folder_to_default_grantee_uses_star_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, calls = _provider(monkeypatch)

    provider._share_folder_to_grantee(
        shared_folder_uid="SF_UID",
        grantee_kind="default",
        manage_records=True,
        manage_users=True,
    )

    assert calls == [
        ["share-folder", "-a", "grant", "-e", "*", "-f", "-p", "on", "-o", "on", "SF_UID"]
    ]


def test_share_folder_to_grantee_rejects_contradictory_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, calls = _provider(monkeypatch)

    with pytest.raises(ValueError, match="default shared-folder grantee"):
        provider._share_folder_to_grantee(
            shared_folder_uid="SF_UID",
            grantee_kind="default",
            identifier="user@example.com",
            manage_records=True,
            manage_users=True,
        )
    with pytest.raises(ValueError, match="user shared-folder grantee requires identifier"):
        provider._share_folder_to_grantee(
            shared_folder_uid="SF_UID",
            grantee_kind="user",
            manage_records=True,
            manage_users=True,
        )
    with pytest.raises(ValueError, match="unsupported shared-folder grantee kind"):
        provider._share_folder_to_grantee(
            shared_folder_uid="SF_UID",
            grantee_kind=cast(Any, "group"),
            identifier="GROUP_UID",
            manage_records=True,
            manage_users=True,
        )

    assert calls == []


def test_revoke_folder_grantee_uses_remove_action(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, calls = _provider(monkeypatch)

    provider._revoke_folder_grantee(
        shared_folder_uid="SF_UID",
        grantee_kind="user",
        identifier="user@example.com",
    )
    provider._revoke_folder_grantee(shared_folder_uid="SF_UID", grantee_kind="default")

    assert calls == [
        ["share-folder", "-a", "remove", "-e", "user@example.com", "-f", "SF_UID"],
        ["share-folder", "-a", "remove", "-e", "*", "-f", "SF_UID"],
    ]


def test_share_record_to_shared_folder_sets_record_permissions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, calls = _provider(monkeypatch)

    provider._share_record_to_shared_folder(
        shared_folder_uid="SF_UID",
        record_uid="REC_UID",
        can_edit=True,
        can_share=False,
    )

    assert calls == [
        ["share-folder", "-a", "grant", "-r", "REC_UID", "-f", "-d", "on", "-s", "off", "SF_UID"]
    ]


def test_set_shared_folder_default_record_share_uses_star_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, calls = _provider(monkeypatch)

    provider._set_shared_folder_default_record_share(
        shared_folder_uid="SF_UID",
        can_edit=False,
        can_share=True,
    )

    assert calls == [
        ["share-folder", "-a", "grant", "-r", "*", "-f", "-d", "off", "-s", "on", "SF_UID"]
    ]


def test_discover_shared_folder_acl_normalizes_get_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, calls = _provider(
        monkeypatch,
        stdout=json.dumps(
            {
                "shared_folder_uid": "SF_UID",
                "manage_records": True,
                "manage_users": False,
                "can_edit": True,
                "can_share": False,
                "users": [
                    {
                        "username": "user@example.com",
                        "manage_records": True,
                        "manage_users": False,
                    }
                ],
                "teams": [
                    {
                        "name": "Engineers",
                        "team_uid": "TEAM_UID",
                        "manage_records": False,
                        "manage_users": True,
                    }
                ],
                "records": [
                    {
                        "record_uid": "REC_UID",
                        "record_name": "Database",
                        "can_edit": True,
                        "can_share": False,
                    }
                ],
            }
        ),
    )

    acl = provider._discover_shared_folder_acl(shared_folder_uid="SF_UID")

    assert calls == [["get", "SF_UID", "--format", "json"]]
    assert acl == {
        "users": [
            {
                "username": "user@example.com",
                "manage_records": True,
                "manage_users": False,
            }
        ],
        "teams": [
            {
                "name": "Engineers",
                "team_uid": "TEAM_UID",
                "manage_records": False,
                "manage_users": True,
            }
        ],
        "records": [
            {
                "record_uid": "REC_UID",
                "record_name": "Database",
                "can_edit": True,
                "can_share": False,
            }
        ],
        "default": {
            "manage_records": True,
            "manage_users": False,
            "can_edit": True,
            "can_share": False,
        },
    }


def test_discover_shared_folder_acl_rejects_non_object_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, _calls = _provider(monkeypatch, stdout="[]")

    with pytest.raises(CapabilityError, match="non-object JSON"):
        provider._discover_shared_folder_acl(shared_folder_uid="SF_UID")


def test_in_process_share_command_flags_unresolved_grantee_warning() -> None:
    assert CommanderCliProvider._in_process_share_command_failed(
        ["share-folder", "-a", "grant"],
        stderr="Share invitation has been sent\nPlease repeat this command when invitation is accepted.",
    )
    assert CommanderCliProvider._in_process_share_command_failed(
        ["share-folder", "-a", "grant"],
        stderr="User labshare@example.com not found",
    )


def test_in_process_share_command_ignores_non_share_warning() -> None:
    assert not CommanderCliProvider._in_process_share_command_failed(
        ["mkdir", "-sf", "/DSK-Test"],
        stderr="User labshare@example.com not found",
    )


def test_in_process_share_command_ignores_remove_warning() -> None:
    assert not CommanderCliProvider._in_process_share_command_failed(
        ["share-folder", "-a", "remove", "-e", "labshare@example.com"],
        stderr="User labshare@example.com not found",
    )
