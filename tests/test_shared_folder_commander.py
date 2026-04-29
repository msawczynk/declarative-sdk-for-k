"""CommanderCliProvider keeper-vault shared-folder apply tests."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.planner import Plan
from keeper_sdk.providers import commander_cli as commander_cli_mod
from keeper_sdk.providers.commander_cli import CommanderCliProvider

RESOURCE_TYPE = "shared_folder"


class _Params:
    def __init__(self) -> None:
        self.current_folder = ""
        self.sync_calls = 0


def _disable_apply_version_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        commander_cli_mod,
        "_ensure_keepercommander_version_for_apply",
        lambda: None,
    )


def _provider(monkeypatch: pytest.MonkeyPatch) -> CommanderCliProvider:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which",
        lambda _bin: "/usr/bin/keeper",
    )
    return CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source={"schema": "keeper-vault.v1", "shared_folders": []},
    )


def _plan(*changes: Change, allow_delete: bool = False) -> Plan:
    plan = Plan(
        manifest_name="vault-shared-folder",
        changes=list(changes),
        order=[change.uid_ref or change.title for change in changes],
    )
    setattr(plan, "allow_delete", allow_delete)
    return plan


def _payload(
    *,
    members: list[dict[str, str]] | None = None,
    permissions: dict[str, bool] | None = None,
) -> dict[str, Any]:
    return {
        "title": "Ops Shared",
        "uid_ref": "sf.ops",
        "manager": "keeper-pam-declarative",
        "members": members or [],
        "permissions": permissions
        if permissions is not None
        else {"manage_records": True, "manage_users": False},
    }


def _change(
    kind: ChangeKind,
    *,
    keeper_uid: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> Change:
    return Change(
        kind=kind,
        uid_ref="sf.ops",
        resource_type=RESOURCE_TYPE,
        title="Ops Shared",
        keeper_uid=keeper_uid,
        before=before or {},
        after=after or {},
    )


def _install_folder_add(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[dict[str, Any]],
) -> None:
    fake_api = types.ModuleType("keepercommander.api")

    def sync_down(params: _Params) -> None:
        params.sync_calls += 1

    fake_api.sync_down = sync_down  # type: ignore[attr-defined]

    fake_folder = types.ModuleType("keepercommander.commands.folder")

    class _FakeFolderAddCommand:
        def execute(self, params: _Params, **kwargs: Any) -> str:
            calls.append({"params": params, **kwargs})
            return "SF_UID"

    fake_folder.FolderAddCommand = _FakeFolderAddCommand  # type: ignore[attr-defined]

    import keepercommander
    import keepercommander.commands

    monkeypatch.setattr(keepercommander, "api", fake_api, raising=False)
    monkeypatch.setattr(keepercommander.commands, "folder", fake_folder, raising=False)
    monkeypatch.setitem(sys.modules, "keepercommander.api", fake_api)
    monkeypatch.setitem(sys.modules, "keepercommander.commands.folder", fake_folder)


def test_commander_apply_creates_shared_folder_with_folder_add_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_apply_version_gate(monkeypatch)
    params = _Params()
    calls: list[dict[str, Any]] = []
    provider = _provider(monkeypatch)
    _install_folder_add(monkeypatch, calls)
    monkeypatch.setattr(provider, "_get_keeper_params", lambda: params)
    monkeypatch.setattr(provider, "_with_keeper_session_refresh", lambda func: func())
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        lambda self, args: pytest.fail(f"unexpected membership command: {args}"),
    )

    outcomes = provider.apply_plan(_plan(_change(ChangeKind.CREATE, after=_payload())))

    assert len(outcomes) == 1
    assert outcomes[0].action == "create"
    assert outcomes[0].keeper_uid == "SF_UID"
    assert calls == [
        {
            "params": params,
            "folder": "Ops Shared",
            "shared_folder": True,
            "user_folder": False,
            "grant": False,
            "manage_records": True,
            "manage_users": False,
            "can_edit": False,
            "can_share": False,
        }
    ]
    assert params.sync_calls == 2


def test_commander_apply_updates_shared_folder_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_apply_version_gate(monkeypatch)
    provider = _provider(monkeypatch)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        lambda self, args: calls.append(args) or "",
    )

    outcomes = provider.apply_plan(
        _plan(
            _change(
                ChangeKind.UPDATE,
                keeper_uid="SF_UID",
                before=_payload(members=[{"email": "alice@example.com", "role": "read"}]),
                after={"members": [{"email": "alice@example.com", "role": "manage"}]},
            )
        )
    )

    assert outcomes[0].action == "update"
    assert outcomes[0].keeper_uid == "SF_UID"
    assert outcomes[0].details["members_granted"] == 1
    assert calls == [
        [
            "share-folder",
            "-a",
            "grant",
            "-e",
            "alice@example.com",
            "-f",
            "-p",
            "on",
            "-o",
            "on",
            "SF_UID",
        ]
    ]


@pytest.mark.parametrize(
    ("before_permission", "after_permission", "manage_records", "manage_users"),
    [
        ("read_only", "manage_records", "on", "off"),
        ("manage_records", "manage_users", "off", "on"),
        ("manage_users", "read_only", "off", "off"),
    ],
)
def test_commander_apply_updates_shared_folder_member_permission_field(
    monkeypatch: pytest.MonkeyPatch,
    before_permission: str,
    after_permission: str,
    manage_records: str,
    manage_users: str,
) -> None:
    _disable_apply_version_gate(monkeypatch)
    provider = _provider(monkeypatch)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        lambda self, args: calls.append(args) or "",
    )

    outcomes = provider.apply_plan(
        _plan(
            _change(
                ChangeKind.UPDATE,
                keeper_uid="SF_UID",
                before=_payload(
                    members=[{"email": "alice@example.com", "permission": before_permission}]
                ),
                after={"members": [{"email": "alice@example.com", "permission": after_permission}]},
            )
        )
    )

    assert outcomes[0].action == "update"
    assert outcomes[0].details["members_granted"] == 1
    assert calls == [
        [
            "share-folder",
            "-a",
            "grant",
            "-e",
            "alice@example.com",
            "-f",
            "-p",
            manage_records,
            "-o",
            manage_users,
            "SF_UID",
        ]
    ]


def test_commander_apply_blocks_shared_folder_member_removal_without_allow_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_apply_version_gate(monkeypatch)
    provider = _provider(monkeypatch)
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        lambda self, args: pytest.fail(f"remove must be blocked before command: {args}"),
    )
    plan = _plan(
        _change(
            ChangeKind.UPDATE,
            keeper_uid="SF_UID",
            before=_payload(
                members=[
                    {"email": "alice@example.com", "role": "manage"},
                    {"email": "bob@example.com", "role": "read"},
                ]
            ),
            after={"members": [{"email": "alice@example.com", "role": "manage"}]},
        )
    )

    with pytest.raises(CapabilityError, match="membership removal requires --allow-delete"):
        provider.apply_plan(plan)

    assert getattr(plan, "requires_allow_delete") is True


def test_commander_apply_blocks_shared_folder_delete_without_allow_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_apply_version_gate(monkeypatch)
    provider = _provider(monkeypatch)
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        lambda self, args: pytest.fail(f"delete must be blocked before command: {args}"),
    )

    with pytest.raises(CapabilityError, match="requires --allow-delete"):
        provider.apply_plan(_plan(_change(ChangeKind.DELETE, keeper_uid="SF_UID")))
