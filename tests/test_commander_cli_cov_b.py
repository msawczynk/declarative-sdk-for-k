"""Coverage slice tests for ``keeper_sdk.providers.commander_cli`` lines 776-1163."""

from __future__ import annotations

import builtins
import json
import sys
import types
from collections.abc import Callable
from typing import Any

import pytest

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.metadata import MARKER_FIELD_LABEL
from keeper_sdk.core.planner import Plan
from keeper_sdk.providers import commander_cli as commander_cli_mod
from keeper_sdk.providers.commander_cli import CommanderCliProvider


class _Params:
    def __init__(self, record_cache: dict[str, dict[str, Any]] | None = None) -> None:
        self.record_cache = record_cache if record_cache is not None else {}
        self.sync_calls = 0


def _allow_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which",
        lambda _bin: "/usr/bin/keeper",
    )
    monkeypatch.delenv("KEEPER_DECLARATIVE_FOLDER", raising=False)


def _disable_apply_version_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        commander_cli_mod,
        "_ensure_keepercommander_version_for_apply",
        lambda: None,
    )


def _provider(
    monkeypatch: pytest.MonkeyPatch,
    *,
    folder_uid: str | None = "folder-uid",
    manifest_source: dict[str, Any] | None = None,
) -> CommanderCliProvider:
    _allow_provider(monkeypatch)
    return CommanderCliProvider(
        folder_uid=folder_uid,
        manifest_source=manifest_source or {"schema": "keeper-vault.v1", "records": []},
    )


def _plan(*changes: Change) -> Plan:
    return Plan(
        manifest_name="demo",
        changes=list(changes),
        order=[change.uid_ref or change.title for change in changes],
    )


def _change(
    kind: ChangeKind,
    *,
    uid_ref: str = "r1",
    title: str = "Login",
    keeper_uid: str | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
) -> Change:
    return Change(
        kind=kind,
        uid_ref=uid_ref,
        resource_type="login",
        title=title,
        keeper_uid=keeper_uid,
        after=after or {},
        reason=reason,
    )


def _record_cache_entry(
    *,
    version: int = 3,
    data_unencrypted: str | bytes | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"version": version}
    if data_unencrypted is not None:
        entry["data_unencrypted"] = data_unencrypted
    return entry


def _install_record_edit(
    monkeypatch: pytest.MonkeyPatch,
    *,
    execute: Callable[[object, dict[str, Any]], None] | None = None,
    sync_down: Callable[[Any], None] | None = None,
) -> None:
    fake_api = types.ModuleType("keepercommander.api")

    def default_sync(params: Any) -> None:
        params.sync_calls += 1

    setattr(fake_api, "sync_down", sync_down or default_sync)

    fake_recordv3 = types.ModuleType("keepercommander.commands.recordv3")

    class _FakeRecordEditCommand:
        def execute(self, params: object, **kwargs: Any) -> None:
            if execute is not None:
                execute(params, kwargs)

    setattr(fake_recordv3, "RecordEditCommand", _FakeRecordEditCommand)

    import keepercommander
    import keepercommander.commands

    monkeypatch.setattr(keepercommander, "api", fake_api, raising=False)
    monkeypatch.setattr(keepercommander.commands, "recordv3", fake_recordv3, raising=False)
    monkeypatch.setitem(sys.modules, "keepercommander.api", fake_api)
    monkeypatch.setitem(sys.modules, "keepercommander.commands.recordv3", fake_recordv3)


def _install_record_add(
    monkeypatch: pytest.MonkeyPatch,
    *,
    execute: Callable[[object, dict[str, Any]], object],
) -> None:
    fake_recordv3 = types.ModuleType("keepercommander.commands.recordv3")

    class _FakeRecordAddCommand:
        def execute(self, params: object, **kwargs: Any) -> object:
            return execute(params, kwargs)

    setattr(fake_recordv3, "RecordAddCommand", _FakeRecordAddCommand)

    import keepercommander.commands

    monkeypatch.setattr(keepercommander.commands, "recordv3", fake_recordv3, raising=False)
    monkeypatch.setitem(sys.modules, "keepercommander.commands.recordv3", fake_recordv3)


def _patch_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(
        name: str,
        globals_: dict[str, Any] | None = None,
        locals_: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "keepercommander" or name.startswith("keepercommander."):
            raise ImportError("missing keepercommander")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_pam_delete_reraises_capability_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers commander_cli.py lines 776-777: PAM delete re-raises CapabilityError."""
    _disable_apply_version_gate(monkeypatch)
    provider = _provider(monkeypatch, manifest_source={"version": "1", "name": "demo"})

    def fail_rm(self: CommanderCliProvider, args: list[str]) -> str:
        assert args == ["rm", "--force", "UID1"]
        raise CapabilityError(reason="rm denied")

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", fail_rm)
    plan = _plan(
        Change(
            kind=ChangeKind.DELETE,
            uid_ref="pam.db",
            resource_type="pamDatabase",
            title="db",
            keeper_uid="UID1",
        )
    )

    with pytest.raises(CapabilityError, match="rm denied"):
        provider.apply_plan(plan)


def test_pam_conflict_and_noop_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers commander_cli.py lines 781 and 790: PAM conflict/noop outcome rows."""
    _disable_apply_version_gate(monkeypatch)
    provider = _provider(monkeypatch, manifest_source={"version": "1", "name": "demo"})
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        lambda self, args: pytest.fail(f"unexpected command: {args}"),
    )
    plan = _plan(
        Change(
            kind=ChangeKind.CONFLICT,
            uid_ref="pam.conflict",
            resource_type="pamDatabase",
            title="db-conflict",
            keeper_uid="UIDC",
            reason="owned elsewhere",
        ),
        Change(
            kind=ChangeKind.NOOP,
            uid_ref="pam.noop",
            resource_type="pamDatabase",
            title="db-noop",
            keeper_uid="UIDN",
        ),
    )

    outcomes = provider.apply_plan(plan)

    assert [(row.action, row.uid_ref, row.keeper_uid) for row in outcomes] == [
        ("conflict", "pam.conflict", "UIDC"),
        ("noop", "pam.noop", "UIDN"),
    ]
    assert outcomes[0].details == {"reason": "owned elsewhere"}


def test_vault_apply_rejects_monkeypatched_unsupported_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 806-813: vault apply unsupported capability error."""
    provider = _provider(monkeypatch)
    monkeypatch.setattr(
        commander_cli_mod,
        "_detect_unsupported_capabilities",
        lambda manifest, *, allow_nested_rotation=False: ["synthetic unsupported"],
    )

    with pytest.raises(CapabilityError, match="synthetic unsupported") as exc_info:
        provider.apply_plan(_plan())

    assert "remove the declarations" in (exc_info.value.next_action or "")


def test_vault_apply_requires_folder_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers commander_cli.py lines 816-819: vault apply requires folder_uid."""
    _disable_apply_version_gate(monkeypatch)
    provider = _provider(monkeypatch, folder_uid=None)

    with pytest.raises(CapabilityError, match="requires a shared folder uid") as exc_info:
        provider.apply_plan(_plan())

    assert "pass --folder-uid" in (exc_info.value.next_action or "")


def test_vault_create_dry_run_records_create_without_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 826-834: vault create dry-run outcome."""
    _disable_apply_version_gate(monkeypatch)
    provider = _provider(monkeypatch)
    monkeypatch.setattr(
        CommanderCliProvider,
        "_vault_add_login_record",
        lambda self, after: pytest.fail("dry-run create must not add a record"),
    )
    plan = _plan(_change(ChangeKind.CREATE, after={"title": "Login"}))

    outcomes = provider.apply_plan(plan, dry_run=True)

    assert len(outcomes) == 1
    assert outcomes[0].action == "create"
    assert outcomes[0].keeper_uid == ""
    assert outcomes[0].details == {"dry_run": True}


def test_vault_update_without_keeper_uid_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 854-862: vault update skip without keeper_uid."""
    _disable_apply_version_gate(monkeypatch)
    provider = _provider(monkeypatch)
    plan = _plan(_change(ChangeKind.UPDATE, after={"title": "Renamed"}))

    outcomes = provider.apply_plan(plan)

    assert outcomes[0].action == "update"
    assert outcomes[0].details == {"skipped": True, "reason": "no keeper_uid on update change"}


def test_vault_update_dry_run_records_existing_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 864-872: vault update dry-run outcome."""
    _disable_apply_version_gate(monkeypatch)
    provider = _provider(monkeypatch)
    monkeypatch.setattr(
        CommanderCliProvider,
        "_vault_apply_login_body_update",
        lambda self, keeper_uid, patch: pytest.fail("dry-run update must not edit body"),
    )
    plan = _plan(_change(ChangeKind.UPDATE, keeper_uid="UID1", after={"title": "Renamed"}))

    outcomes = provider.apply_plan(plan, dry_run=True)

    assert outcomes[0].action == "update"
    assert outcomes[0].keeper_uid == "UID1"
    assert outcomes[0].details == {"dry_run": True}


def test_vault_update_empty_patch_writes_marker_without_body_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 873-889: vault update marker path with empty patch."""
    _disable_apply_version_gate(monkeypatch)
    marker_calls: list[tuple[str, str | None]] = []
    provider = _provider(monkeypatch)
    monkeypatch.setattr(
        CommanderCliProvider,
        "_vault_apply_login_body_update",
        lambda self, keeper_uid, patch: pytest.fail("empty patch must not edit body"),
    )
    monkeypatch.setattr(
        CommanderCliProvider,
        "_write_marker",
        lambda self, keeper_uid, marker: marker_calls.append((keeper_uid, marker.get("uid_ref"))),
    )
    plan = _plan(_change(ChangeKind.UPDATE, keeper_uid="UID1", after={}))

    outcomes = provider.apply_plan(plan)

    assert marker_calls == [("UID1", "r1")]
    assert outcomes[0].details == {"marker_written": True, "record_updated": False}


def test_vault_delete_without_keeper_uid_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 893-906: vault delete skip without keeper_uid."""
    _disable_apply_version_gate(monkeypatch)
    provider = _provider(monkeypatch)
    plan = _plan(_change(ChangeKind.DELETE))

    outcomes = provider.apply_plan(plan)

    assert outcomes[0].action == "delete"
    assert outcomes[0].details["skipped"] is True
    assert outcomes[0].details["reason"] == "no keeper_uid on delete change"


def test_vault_delete_dry_run_records_keeper_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 907-920: vault delete dry-run outcome."""
    _disable_apply_version_gate(monkeypatch)
    provider = _provider(monkeypatch)
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        lambda self, args: pytest.fail(f"dry-run delete must not rm: {args}"),
    )
    plan = _plan(_change(ChangeKind.DELETE, keeper_uid="UID1"))

    outcomes = provider.apply_plan(plan, dry_run=True)

    assert outcomes[0].action == "delete"
    assert outcomes[0].keeper_uid == "UID1"
    assert outcomes[0].details["dry_run"] is True
    assert outcomes[0].details["keeper_uid"] == "UID1"


def test_vault_delete_success_marks_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers commander_cli.py lines 921-936: vault delete rm success and removed flag."""
    _disable_apply_version_gate(monkeypatch)
    calls: list[list[str]] = []
    provider = _provider(monkeypatch)

    def record_rm(self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        return ""

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", record_rm)
    plan = _plan(_change(ChangeKind.DELETE, keeper_uid="UID1"))

    outcomes = provider.apply_plan(plan)

    assert calls == [["rm", "--force", "UID1"]]
    assert outcomes[0].details["removed"] is True


def test_vault_delete_reraises_capability_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers commander_cli.py lines 932-935: vault delete re-raises rm CapabilityError."""
    _disable_apply_version_gate(monkeypatch)
    provider = _provider(monkeypatch)

    def fail_rm(self: CommanderCliProvider, args: list[str]) -> str:
        assert args == ["rm", "--force", "UID1"]
        raise CapabilityError(reason="rm failed")

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", fail_rm)
    plan = _plan(_change(ChangeKind.DELETE, keeper_uid="UID1"))

    with pytest.raises(CapabilityError, match="rm failed"):
        provider.apply_plan(plan)


def test_vault_conflict_and_noop_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers commander_cli.py lines 939 and 948: vault conflict/noop outcome rows."""
    _disable_apply_version_gate(monkeypatch)
    provider = _provider(monkeypatch)
    plan = _plan(
        _change(ChangeKind.CONFLICT, uid_ref="conflict", keeper_uid="UIDC", reason="blocked"),
        _change(ChangeKind.NOOP, uid_ref="noop", keeper_uid="UIDN"),
    )

    outcomes = provider.apply_plan(plan)

    assert [(row.action, row.uid_ref, row.keeper_uid) for row in outcomes] == [
        ("conflict", "conflict", "UIDC"),
        ("noop", "noop", "UIDN"),
    ]
    assert outcomes[0].details == {"reason": "blocked"}


def test_vault_custom_field_label_prefers_name() -> None:
    """Covers commander_cli.py lines 957-959: custom label fallback to name."""
    assert CommanderCliProvider._vault_custom_field_label({"name": "Api Key"}) == "api key"


def test_vault_merge_custom_skips_non_dict_existing() -> None:
    """Covers commander_cli.py line 982: non-dict existing custom entries are ignored."""
    out = CommanderCliProvider._vault_merge_custom_for_update(
        ["not-a-dict", {"label": "keep", "value": ["old"]}],
        [],
    )

    assert out == [{"label": "keep", "value": ["old"]}]


def test_vault_merge_custom_replaces_matching_label() -> None:
    """Covers commander_cli.py lines 984-986: patch replaces existing custom label."""
    out = CommanderCliProvider._vault_merge_custom_for_update(
        [{"label": "Env", "value": ["old"]}],
        [{"label": "env", "value": ["new"]}],
    )

    assert out == [{"label": "env", "value": ["new"]}]


def test_vault_merge_custom_appends_unused_patch_label() -> None:
    """Covers commander_cli.py lines 989-991: unused patch labels are appended."""
    out = CommanderCliProvider._vault_merge_custom_for_update(
        [{"label": "a", "value": ["1"]}],
        [{"label": "b", "value": ["2"]}],
    )

    assert [entry["label"] for entry in out] == ["a", "b"]


def test_vault_merge_custom_preserves_omitted_marker() -> None:
    """Covers commander_cli.py lines 993-1003: omitted marker custom field is preserved."""
    marker = {"label": MARKER_FIELD_LABEL, "value": ["marker"]}
    out = CommanderCliProvider._vault_merge_custom_for_update(
        [{"label": "env", "value": ["old"]}, marker],
        [{"label": "env", "value": ["new"]}],
    )

    assert out == [{"label": "env", "value": ["new"]}, marker]


def test_vault_merge_custom_defensively_reappends_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py line 1003: defensive marker append fallback."""
    original_label = CommanderCliProvider._vault_custom_field_label
    marker_calls = 0

    def flaky_marker_label(entry: dict[str, Any]) -> str:
        nonlocal marker_calls
        if entry.get("label") == MARKER_FIELD_LABEL:
            marker_calls += 1
            if marker_calls <= 2:
                return "temporarily-hidden-marker"
        return original_label(entry)

    monkeypatch.setattr(
        CommanderCliProvider,
        "_vault_custom_field_label",
        staticmethod(flaky_marker_label),
    )

    marker = {"label": MARKER_FIELD_LABEL, "value": ["marker"]}
    out = CommanderCliProvider._vault_merge_custom_for_update([marker], [])

    assert out == [marker, marker]


def test_vault_patch_custom_non_list_is_ignored() -> None:
    """Covers commander_cli.py lines 1017-1018: non-list custom patch is ignored."""
    existing = {"type": "login", "title": "T", "custom": [{"label": "keep"}]}

    out = CommanderCliProvider._vault_patch_login_record_data(existing, {"custom": "bad"})

    assert out == existing
    assert out is not existing


def test_vault_patch_custom_list_merges_with_existing() -> None:
    """Covers commander_cli.py line 1019: list custom patch merges through helper."""
    existing = {"type": "login", "custom": [{"label": "env", "value": ["old"]}]}

    out = CommanderCliProvider._vault_patch_login_record_data(
        existing,
        {"custom": [{"label": "env", "value": ["new"]}]},
    )

    assert out["custom"] == [{"label": "env", "value": ["new"]}]


def test_vault_apply_login_body_update_noops_on_empty_patch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1029-1030: empty vault body patch returns early."""
    provider = _provider(monkeypatch)
    monkeypatch.setattr(
        provider,
        "_with_keeper_session_refresh",
        lambda func: pytest.fail("empty patch must not open a session"),
    )

    provider._vault_apply_login_body_update("UID1", {})


def test_vault_apply_login_body_update_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1031-1038: update body import error wrapper."""
    provider = _provider(monkeypatch)
    _patch_import_error(monkeypatch)

    with pytest.raises(CapabilityError, match="keepercommander unavailable") as exc_info:
        provider._vault_apply_login_body_update("UID1", {"title": "New"})

    assert "install Commander Python package" in (exc_info.value.next_action or "")


def test_vault_apply_login_body_update_missing_cache_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1040-1048: cache miss after sync is a CapabilityError."""
    provider = _provider(monkeypatch)
    params = _Params({})
    _install_record_edit(monkeypatch)
    monkeypatch.setattr(provider, "_get_keeper_params", lambda: params)
    monkeypatch.setattr(provider, "_with_keeper_session_refresh", lambda func: func())

    with pytest.raises(CapabilityError, match="record UID1 not found"):
        provider._vault_apply_login_body_update("UID1", {"title": "New"})

    assert params.sync_calls == 1


def test_vault_apply_login_body_update_rejects_non_v3_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1049-1060: non-v3 cache record is rejected."""
    provider = _provider(monkeypatch)
    params = _Params({"UID1": _record_cache_entry(version=2, data_unencrypted="{}")})
    _install_record_edit(monkeypatch)
    monkeypatch.setattr(provider, "_get_keeper_params", lambda: params)
    monkeypatch.setattr(provider, "_with_keeper_session_refresh", lambda func: func())

    with pytest.raises(CapabilityError, match="must be record version 3"):
        provider._vault_apply_login_body_update("UID1", {"title": "New"})


def test_vault_apply_login_body_update_requires_decrypted_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1061-1066: missing decrypted data is rejected."""
    provider = _provider(monkeypatch)
    params = _Params({"UID1": _record_cache_entry(version=3)})
    _install_record_edit(monkeypatch)
    monkeypatch.setattr(provider, "_get_keeper_params", lambda: params)
    monkeypatch.setattr(provider, "_with_keeper_session_refresh", lambda func: func())

    with pytest.raises(CapabilityError, match="has no decrypted data"):
        provider._vault_apply_login_body_update("UID1", {"title": "New"})


def test_vault_apply_login_body_update_returns_when_merge_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1067-1071: unchanged merge skips RecordEditCommand."""
    provider = _provider(monkeypatch)
    params = _Params(
        {
            "UID1": _record_cache_entry(
                data_unencrypted=json.dumps({"type": "login", "title": "Old"})
            )
        }
    )

    def fail_execute(params_arg: object, kwargs: dict[str, Any]) -> None:
        pytest.fail(f"unchanged merge must not edit: {params_arg}, {kwargs}")

    _install_record_edit(monkeypatch, execute=fail_execute)
    monkeypatch.setattr(provider, "_get_keeper_params", lambda: params)
    monkeypatch.setattr(provider, "_with_keeper_session_refresh", lambda func: func())

    provider._vault_apply_login_body_update("UID1", {"uid_ref": "ignored"})


def test_vault_apply_login_body_update_success_with_bytes_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1067-1082: bytes data edit sets update_record_v3."""
    provider = _provider(monkeypatch)
    existing = {"type": "login", "title": "Old", "fields": []}
    params = _Params(
        {"UID1": _record_cache_entry(data_unencrypted=json.dumps(existing).encode("utf-8"))}
    )
    seen: list[dict[str, Any]] = []

    def execute(params_arg: object, kwargs: dict[str, Any]) -> None:
        assert params_arg is params
        seen.append(kwargs)
        kwargs["return_result"]["update_record_v3"] = True

    _install_record_edit(monkeypatch, execute=execute)
    monkeypatch.setattr(provider, "_get_keeper_params", lambda: params)
    monkeypatch.setattr(provider, "_with_keeper_session_refresh", lambda func: func())

    provider._vault_apply_login_body_update("UID1", {"title": "New"})

    assert json.loads(seen[0]["data"])["title"] == "New"
    assert seen[0]["record"] == "UID1"


def test_vault_apply_login_body_update_success_with_str_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1067-1082: str data edit sets update_record_v3."""
    provider = _provider(monkeypatch)
    params = _Params(
        {
            "UID1": _record_cache_entry(
                data_unencrypted=json.dumps({"type": "login", "title": "Old"})
            )
        }
    )
    seen: list[dict[str, Any]] = []

    def execute(params_arg: object, kwargs: dict[str, Any]) -> None:
        assert params_arg is params
        seen.append(kwargs)
        kwargs["return_result"]["update_record_v3"] = True

    _install_record_edit(monkeypatch, execute=execute)
    monkeypatch.setattr(provider, "_get_keeper_params", lambda: params)
    monkeypatch.setattr(provider, "_with_keeper_session_refresh", lambda func: func())

    provider._vault_apply_login_body_update("UID1", {"title": "New"})

    assert json.loads(seen[0]["data"])["title"] == "New"


def test_vault_apply_login_body_update_rejects_falsey_edit_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1082-1096: falsey edit result includes stderr tail."""
    provider = _provider(monkeypatch)
    params = _Params(
        {
            "UID1": _record_cache_entry(
                data_unencrypted=json.dumps({"type": "login", "title": "Old"})
            )
        }
    )

    def execute(params_arg: object, kwargs: dict[str, Any]) -> None:
        assert params_arg is params
        assert kwargs["return_result"] == {}
        print("bad edit shape", file=sys.stderr)

    _install_record_edit(monkeypatch, execute=execute)
    monkeypatch.setattr(provider, "_get_keeper_params", lambda: params)
    monkeypatch.setattr(provider, "_with_keeper_session_refresh", lambda func: func())

    with pytest.raises(CapabilityError, match="stderr: bad edit shape"):
        provider._vault_apply_login_body_update("UID1", {"title": "New"})


def test_vault_apply_login_body_update_reraises_capability_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1098-1101: outer CapabilityError is re-raised."""
    provider = _provider(monkeypatch)
    _install_record_edit(monkeypatch)

    def fail_refresh(func: Callable[[], None]) -> None:
        _ = func
        raise CapabilityError(reason="session denied")

    monkeypatch.setattr(provider, "_with_keeper_session_refresh", fail_refresh)

    with pytest.raises(CapabilityError, match="session denied"):
        provider._vault_apply_login_body_update("UID1", {"title": "New"})


def test_vault_apply_login_body_update_wraps_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1102-1106: unexpected update exception is wrapped."""
    provider = _provider(monkeypatch)
    _install_record_edit(monkeypatch)
    monkeypatch.setattr(
        provider,
        "_with_keeper_session_refresh",
        lambda func: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(CapabilityError, match="RuntimeError: boom") as exc_info:
        provider._vault_apply_login_body_update("UID1", {"title": "New"})

    assert "inspect Commander stderr/stdout" in (exc_info.value.next_action or "")


def test_vault_add_login_record_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers commander_cli.py lines 1110-1116: record-add import error wrapper."""
    provider = _provider(monkeypatch)
    _patch_import_error(monkeypatch)

    with pytest.raises(CapabilityError, match="cannot create vault record"):
        provider._vault_add_login_record({"title": "Login"})


def test_vault_add_login_record_success_strips_string_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1118-1153 and 1163: record-add string UID success."""
    provider = _provider(monkeypatch)
    params = _Params()
    seen: list[dict[str, Any]] = []

    def execute(params_arg: object, kwargs: dict[str, Any]) -> object:
        assert params_arg is params
        seen.append(kwargs)
        return " UID1 \n"

    _install_record_add(monkeypatch, execute=execute)
    monkeypatch.setattr(provider, "_get_keeper_params", lambda: params)
    monkeypatch.setattr(provider, "_with_keeper_session_refresh", lambda func: func())

    uid = provider._vault_add_login_record(
        {
            "title": "Login",
            "fields": [{"type": "login", "value": ["u"]}],
            "custom": [{"label": "env", "value": ["dev"]}],
            "notes": "remember",
        }
    )

    data = json.loads(seen[0]["data"])
    assert uid == "UID1"
    assert data == {
        "type": "login",
        "title": "Login",
        "fields": [{"type": "login", "value": ["u"]}],
        "custom": [{"label": "env", "value": ["dev"]}],
        "notes": "remember",
    }
    assert seen[0]["force"] is False
    assert seen[0]["folder"] == "folder-uid"
    assert seen[0]["attach"] == []


def test_vault_add_login_record_decodes_bytes_uid_and_omits_blank_notes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1124-1127 and 1154-1155: bytes UID success."""
    provider = _provider(monkeypatch)
    params = _Params()
    seen: list[dict[str, Any]] = []

    def execute(params_arg: object, kwargs: dict[str, Any]) -> object:
        assert params_arg is params
        seen.append(json.loads(kwargs["data"]))
        return b" UID-BYTES \n"

    _install_record_add(monkeypatch, execute=execute)
    monkeypatch.setattr(provider, "_get_keeper_params", lambda: params)
    monkeypatch.setattr(provider, "_with_keeper_session_refresh", lambda func: func())

    uid = provider._vault_add_login_record({"title": "Login", "notes": "   "})

    assert uid == "UID-BYTES"
    assert "notes" not in seen[0]


def test_vault_add_login_record_coerces_non_string_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1156-1157: non-string record-add UID coercion."""
    provider = _provider(monkeypatch)
    _install_record_add(monkeypatch, execute=lambda params, kwargs: 12345)
    monkeypatch.setattr(provider, "_get_keeper_params", lambda: _Params())
    monkeypatch.setattr(provider, "_with_keeper_session_refresh", lambda func: func())

    assert provider._vault_add_login_record({"title": "Login"}) == "12345"


def test_vault_add_login_record_reraises_capability_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1141-1144: record-add CapabilityError is re-raised."""
    provider = _provider(monkeypatch)
    _install_record_add(monkeypatch, execute=lambda params, kwargs: "UID")

    def fail_refresh(func: Callable[[], object]) -> object:
        _ = func
        raise CapabilityError(reason="folder denied")

    monkeypatch.setattr(provider, "_with_keeper_session_refresh", fail_refresh)

    with pytest.raises(CapabilityError, match="folder denied"):
        provider._vault_add_login_record({"title": "Login"})


def test_vault_add_login_record_wraps_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1145-1149: record-add unexpected exception wrapper."""
    provider = _provider(monkeypatch)
    _install_record_add(monkeypatch, execute=lambda params, kwargs: "UID")
    monkeypatch.setattr(
        provider,
        "_with_keeper_session_refresh",
        lambda func: (_ for _ in ()).throw(RuntimeError("add boom")),
    )

    with pytest.raises(CapabilityError, match="RuntimeError: add boom") as exc_info:
        provider._vault_add_login_record({"title": "Login"})

    assert "verify folder permissions" in (exc_info.value.next_action or "")


@pytest.mark.parametrize("returned_uid", ["  ", b" \n", None])
def test_vault_add_login_record_rejects_empty_uid(
    monkeypatch: pytest.MonkeyPatch,
    returned_uid: object,
) -> None:
    """Covers commander_cli.py lines 1158-1162: empty record-add UID is rejected."""
    provider = _provider(monkeypatch)
    _install_record_add(monkeypatch, execute=lambda params, kwargs: returned_uid)
    monkeypatch.setattr(provider, "_get_keeper_params", lambda: _Params())
    monkeypatch.setattr(provider, "_with_keeper_session_refresh", lambda func: func())

    with pytest.raises(CapabilityError, match="did not return a record UID") as exc_info:
        provider._vault_add_login_record({"title": "Login"})

    assert "record-add" in (exc_info.value.next_action or "")
