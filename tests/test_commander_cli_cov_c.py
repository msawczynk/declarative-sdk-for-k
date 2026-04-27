"""Coverage tests for Commander CLI provider long-tail branches."""

from __future__ import annotations

import builtins
import json
import sys
import types
from typing import Any

import pytest

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.metadata import MARKER_FIELD_LABEL, encode_marker, serialize_marker
from keeper_sdk.core.planner import Plan
from keeper_sdk.providers import commander_cli as commander_cli_mod
from keeper_sdk.providers.commander_cli import (
    CommanderCliProvider,
    build_pam_rotation_edit_argvs,
    build_post_import_tuning_argvs,
)


def _provider(
    monkeypatch: pytest.MonkeyPatch,
    *,
    manifest_source: dict[str, Any] | None = None,
    stdout: str = "",
) -> CommanderCliProvider:
    monkeypatch.setattr(
        commander_cli_mod.shutil,
        "which",
        lambda _bin: "/usr/bin/keeper",
    )
    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", lambda self, args: stdout)
    return CommanderCliProvider(
        folder_uid="folder-uid",
        manifest_source=manifest_source or {},
    )


class _FakeTypedRecord:
    def __init__(self, custom: list[Any] | None = None) -> None:
        self.custom = custom or []


def _install_marker_modules(
    monkeypatch: pytest.MonkeyPatch,
    *,
    record: object,
    updates: list[tuple[object, object]] | None = None,
) -> None:
    fake_api = types.ModuleType("keepercommander.api")
    fake_record_management = types.ModuleType("keepercommander.record_management")
    fake_vault = types.ModuleType("keepercommander.vault")
    fake_root = types.ModuleType("keepercommander")

    class _FakeKeeperRecord:
        @staticmethod
        def load(_params: object, _keeper_uid: str) -> object:
            return record

    class _FakeTypedField:
        @staticmethod
        def new_field(field_type: str, value: str, label: str) -> object:
            return types.SimpleNamespace(type=field_type, value=[value], label=label)

    def update_record(params: object, updated_record: object) -> None:
        if updates is not None:
            updates.append((params, updated_record))

    fake_api.sync_down = lambda _params: None  # type: ignore[attr-defined]
    fake_record_management.update_record = update_record  # type: ignore[attr-defined]
    fake_vault.KeeperRecord = _FakeKeeperRecord  # type: ignore[attr-defined]
    fake_vault.TypedField = _FakeTypedField  # type: ignore[attr-defined]
    fake_vault.TypedRecord = _FakeTypedRecord  # type: ignore[attr-defined]
    fake_root.api = fake_api  # type: ignore[attr-defined]
    fake_root.record_management = fake_record_management  # type: ignore[attr-defined]
    fake_root.vault = fake_vault  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "keepercommander", fake_root)
    monkeypatch.setitem(sys.modules, "keepercommander.api", fake_api)
    monkeypatch.setitem(sys.modules, "keepercommander.record_management", fake_record_management)
    monkeypatch.setitem(sys.modules, "keepercommander.vault", fake_vault)


def test_synthetic_reference_config_no_project_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py line 1234."""
    provider = _provider(
        monkeypatch,
        manifest_source={
            "gateways": [{"mode": "reference_existing", "name": "Gateway"}],
            "pam_configurations": [{"uid_ref": "cfg", "title": "Config"}],
        },
    )

    assert provider._synthetic_reference_configuration_record() is None


def test_synthetic_reference_config_missing_resolved_folder_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py line 1238."""
    provider = _provider(
        monkeypatch,
        manifest_source={
            "name": "Project",
            "gateways": [{"mode": "reference_existing", "name": "Gateway"}],
            "pam_configurations": [{"uid_ref": "cfg", "title": "Config"}],
        },
    )
    monkeypatch.setattr(
        CommanderCliProvider,
        "_maybe_resolve_project_resources_folder",
        lambda self, project_name: None,
    )

    assert provider._synthetic_reference_configuration_record() is None


def test_reference_scaffold_requires_both_project_shared_folders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py line 1291."""
    provider = _provider(monkeypatch)
    monkeypatch.setattr(CommanderCliProvider, "_ensure_folder_exists", lambda self, path: None)
    monkeypatch.setattr(
        CommanderCliProvider,
        "_ensure_shared_folder_exists",
        lambda self, path: None,
    )
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        lambda self, args: json.dumps([{"name": "Project - Resources", "uid": "resources-uid"}]),
    )

    with pytest.raises(CapabilityError, match="did not return the shared folders"):
        provider._ensure_reference_project_scaffold(
            project_name="Project",
            gateway_app_uid="app-uid",
        )


def test_share_folder_to_ksm_app_ignores_already_shared_and_reraises_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1525-1530."""
    provider = _provider(monkeypatch)
    calls: list[list[str]] = []

    def fake_run(_self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        if len(calls) == 1:
            raise CapabilityError(reason="share failed", context={"stderr": "Already shared"})
        raise CapabilityError(reason="share failed", context={"stderr": "permission denied"})

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", fake_run)

    provider._share_folder_to_ksm_app(folder_uid="folder-uid", app_uid="app-uid")
    with pytest.raises(CapabilityError, match="share failed"):
        provider._share_folder_to_ksm_app(folder_uid="folder-uid", app_uid="app-uid")


def test_reference_configuration_reports_missing_gateway_and_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1551 and 1556."""
    provider = _provider(monkeypatch)
    payload = {"pam_configuration": {"title": "Config", "gateway_name": "Gateway"}}
    monkeypatch.setattr(CommanderCliProvider, "_pam_gateway_rows", lambda self: [])
    monkeypatch.setattr(CommanderCliProvider, "_pam_config_rows", lambda self: [])

    with pytest.raises(CapabilityError, match="gateway 'Gateway' not found"):
        provider._resolve_reference_configuration(payload)

    monkeypatch.setattr(
        CommanderCliProvider,
        "_pam_gateway_rows",
        lambda self: [
            {
                "gateway_name": "Gateway",
                "gateway_uid": "gateway-uid",
                "app_uid": "app-uid",
                "app_title": "",
            }
        ],
    )

    with pytest.raises(CapabilityError, match="PAM configuration 'Config' not found"):
        provider._resolve_reference_configuration(payload)


def test_pam_gateway_rows_handles_non_dict_payload_and_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1585 and 1589."""
    provider = _provider(monkeypatch, stdout=json.dumps(["not-a-dict-payload"]))
    assert provider._pam_gateway_rows() == []

    provider = _provider(
        monkeypatch,
        stdout=json.dumps(
            {
                "gateways": [
                    "not-a-row",
                    {
                        "ksm_app_name": "App",
                        "ksm_app_uid": "app-uid",
                        "gateway_name": "Gateway",
                        "gateway_uid": "gateway-uid",
                    },
                ]
            }
        ),
    )

    assert provider._pam_gateway_rows() == [
        {
            "app_title": "App",
            "app_uid": "app-uid",
            "gateway_name": "Gateway",
            "gateway_uid": "gateway-uid",
        }
    ]


def test_ksm_app_rows_handles_list_payload_non_dict_items_and_other_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1608-1611 and 1615."""
    provider = _provider(
        monkeypatch,
        stdout=json.dumps(["not-a-row", {"title": "App", "uid": "app-uid"}]),
    )
    assert provider._ksm_app_rows() == [{"app_title": "App", "app_uid": "app-uid"}]
    assert provider._ksm_app_rows() == [{"app_title": "App", "app_uid": "app-uid"}]

    provider = _provider(monkeypatch, stdout=json.dumps("not-a-supported-shape"))
    assert provider._ksm_app_rows() == []


def test_gateway_bound_app_name_reports_unlabelled_and_unreadable_app_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1646 and 1655-1656."""
    provider = _provider(monkeypatch)

    actual, issue = provider._gateway_bound_app_name({"app_title": "", "app_uid": ""})
    assert actual is None
    assert issue is not None
    assert "neither a KSM app name nor a KSM app UID" in issue

    def fail_rows(_self: CommanderCliProvider) -> list[dict[str, str]]:
        raise CapabilityError(reason="cannot list apps")

    monkeypatch.setattr(CommanderCliProvider, "_ksm_app_rows", fail_rows)
    actual, issue = provider._gateway_bound_app_name({"app_title": "", "app_uid": "app-uid"})

    assert actual is None
    assert issue is not None
    assert "could not be read" in issue


def test_pam_config_rows_handles_non_dict_payload_and_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1688 and 1692."""
    provider = _provider(monkeypatch, stdout=json.dumps(["not-a-dict-payload"]))
    assert provider._pam_config_rows() == []

    provider = _provider(
        monkeypatch,
        stdout=json.dumps(
            {
                "configurations": [
                    "not-a-row",
                    {
                        "uid": "cfg-uid",
                        "config_name": "Config",
                        "gateway_uid": "gateway-uid",
                        "shared_folder": "not-a-dict",
                    },
                ]
            }
        ),
    )

    assert provider._pam_config_rows() == [
        {
            "config_uid": "cfg-uid",
            "config_name": "Config",
            "gateway_uid": "gateway-uid",
            "shared_folder_title": "",
            "shared_folder_uid": "",
        }
    ]


def test_write_marker_reports_import_error_and_non_typed_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1719-1720 and 1730."""
    provider = _provider(monkeypatch)
    marker = encode_marker(uid_ref="res", manifest="Project", resource_type="pamMachine")
    original_import = builtins.__import__

    def fake_import(
        name: str,
        globals_: dict[str, Any] | None = None,
        locals_: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "keepercommander":
            raise ImportError("blocked")
        return original_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(CapabilityError, match="keepercommander unavailable"):
        provider._write_marker("record-uid", marker)

    monkeypatch.setattr(builtins, "__import__", original_import)
    _install_marker_modules(monkeypatch, record=object())
    provider._keeper_params = object()

    with pytest.raises(CapabilityError, match="not a TypedRecord"):
        provider._write_marker("record-uid", marker)


def test_write_marker_updates_existing_marker_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers commander_cli.py lines 1737-1739 and 1741-1742."""
    existing_field = types.SimpleNamespace(label=MARKER_FIELD_LABEL, type="old", value=["old"])
    record = _FakeTypedRecord(custom=[existing_field])
    updates: list[tuple[object, object]] = []
    _install_marker_modules(monkeypatch, record=record, updates=updates)
    provider = _provider(monkeypatch)
    provider._keeper_params = object()
    marker = encode_marker(uid_ref="res", manifest="Project", resource_type="pamMachine")

    provider._write_marker("record-uid", marker)

    assert existing_field.type == "text"
    assert existing_field.value == [serialize_marker(marker)]
    assert updates == [(provider._keeper_params, record)]


def test_write_marker_propagates_capability_error_and_wraps_generic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1752-1755."""
    record = _FakeTypedRecord()
    _install_marker_modules(monkeypatch, record=record)
    provider = _provider(monkeypatch)
    marker = encode_marker(uid_ref="res", manifest="Project", resource_type="pamMachine")

    def raise_capability(_self: CommanderCliProvider, _operation: object) -> object:
        raise CapabilityError(reason="keep me")

    monkeypatch.setattr(CommanderCliProvider, "_with_keeper_session_refresh", raise_capability)
    with pytest.raises(CapabilityError) as exc_info:
        provider._write_marker("record-uid", marker)
    assert exc_info.value.reason == "keep me"

    def raise_runtime(_self: CommanderCliProvider, _operation: object) -> object:
        raise RuntimeError("wrap me")

    monkeypatch.setattr(CommanderCliProvider, "_with_keeper_session_refresh", raise_runtime)
    with pytest.raises(CapabilityError) as exc_info:
        provider._write_marker("record-uid", marker)
    assert "cannot write ownership marker: RuntimeError: wrap me" in exc_info.value.reason


def test_project_scaffold_resolution_reports_missing_project_and_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1773 and 1785."""
    provider = _provider(monkeypatch)
    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", lambda self, args: json.dumps([]))

    with pytest.raises(CapabilityError, match="project folder 'Project'"):
        provider._resolve_project_scaffold_folders("Project")

    calls: list[list[str]] = []

    def fake_run(_self: CommanderCliProvider, args: list[str]) -> str:
        calls.append(args)
        if len(calls) == 1:
            return json.dumps([{"name": "Project", "uid": "project-uid"}])
        return json.dumps([])

    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", fake_run)
    with pytest.raises(CapabilityError, match="resources folder 'Project - Resources'"):
        provider._resolve_project_scaffold_folders("Project")


def test_is_silent_failure_returns_false_for_non_silent_command() -> None:
    """Covers commander_cli.py line 1896."""
    assert (
        CommanderCliProvider._is_silent_failure(
            ["whoami"],
            stdout="",
            stderr="No such folder or record",
        )
        is False
    )


def test_in_process_read_wrappers_wrap_session_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1943-1944, 2095-2096, and 2139-2140."""
    provider = _provider(monkeypatch)

    def fail_refresh(_self: CommanderCliProvider, _operation: object) -> object:
        raise RuntimeError("in-process failed")

    monkeypatch.setattr(CommanderCliProvider, "_with_keeper_session_refresh", fail_refresh)

    cases = (
        (
            provider._run_pam_list_in_process,
            ["pam", "gateway", "list", "--format", "json"],
            "in-process keeper pam gateway list --format json failed",
        ),
        (
            provider._run_ls_in_process,
            ["ls", "folder-uid", "--format", "json"],
            "in-process keeper ls failed",
        ),
        (
            provider._run_record_get_in_process,
            ["get", "record-uid", "--format", "json"],
            "in-process keeper get failed",
        ),
    )
    for method, args, expected in cases:
        with pytest.raises(CapabilityError) as exc_info:
            method(args)
        assert expected in exc_info.value.reason
        assert "RuntimeError: in-process failed" in exc_info.value.reason


def test_pam_project_extend_in_process_executes_extend_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 1986-1991."""
    module = types.ModuleType("keepercommander.commands.pam_import.extend")
    seen: list[tuple[object, dict[str, object]]] = []

    class _FakeExtend:
        def execute(self, params: object, **kwargs: object) -> None:
            seen.append((params, kwargs))
            print("extend ok")

    module.PAMProjectExtendCommand = _FakeExtend  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "keepercommander.commands.pam_import.extend", module)
    provider = _provider(monkeypatch)
    params = object()
    provider._keeper_params = params

    output = provider._run_pam_project_in_process(
        [
            "pam",
            "project",
            "extend",
            "--config",
            "Config",
            "--file",
            "/tmp/manifest.json",
            "--dry-run",
        ]
    )

    assert output.strip() == "extend ok"
    assert seen == [
        (
            params,
            {"config": "Config", "file_name": "/tmp/manifest.json", "dry_run": True},
        )
    ]


def test_get_keeper_params_wraps_generic_helper_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 2228-2229."""
    import keeper_sdk.auth as auth_mod

    class _FailingEnvHelper:
        def load_keeper_creds(self) -> dict[str, str]:
            raise RuntimeError("no credentials")

    monkeypatch.delenv("KEEPER_SDK_LOGIN_HELPER", raising=False)
    monkeypatch.setattr(auth_mod, "EnvLoginHelper", _FailingEnvHelper)
    provider = _provider(monkeypatch)

    with pytest.raises(CapabilityError) as exc_info:
        provider._get_keeper_params()

    assert "in-process Commander login failed: RuntimeError: no credentials" in (
        exc_info.value.reason
    )


def test_post_import_tuning_requires_record_and_empty_source_noops() -> None:
    """Covers commander_cli.py lines 2274 and 2299."""
    with pytest.raises(ValueError, match="record is required"):
        build_post_import_tuning_argvs("", {})

    plan = Plan(manifest_name="Project", changes=[], order=[])
    assert (
        commander_cli_mod._resolve_post_import_tuning_argvs(
            {},
            plan=plan,
            live_records=[],
            changes=[],
        )
        == {}
    )


def test_resolve_post_import_tuning_skips_changes_without_uid_ref() -> None:
    """Covers commander_cli.py line 2306."""
    plan = Plan(manifest_name="Project", changes=[], order=[])
    change = Change(
        kind=ChangeKind.CREATE,
        uid_ref=None,
        resource_type="pamMachine",
        title="machine",
    )

    assert (
        commander_cli_mod._resolve_post_import_tuning_argvs(
            {
                "resources": [
                    {"uid_ref": "machine", "pam_settings": {"options": {"connections": "on"}}}
                ]
            },
            plan=plan,
            live_records=[],
            changes=[change],
        )
        == {}
    )


def test_preview_post_import_tuning_empty_and_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers commander_cli.py lines 2357 and 2370-2371."""
    assert (
        commander_cli_mod._preview_post_import_tuning_argvs(
            Change(kind=ChangeKind.CREATE, uid_ref=None, resource_type="pamMachine", title="M"),
            {},
        )
        == []
    )

    def fail_build(*_args: object, **_kwargs: object) -> list[list[str]]:
        raise ValueError("unresolved")

    monkeypatch.setattr(commander_cli_mod, "build_post_import_tuning_argvs", fail_build)
    change = Change(kind=ChangeKind.CREATE, uid_ref="res", resource_type="pamMachine", title="M")

    assert (
        commander_cli_mod._preview_post_import_tuning_argvs(
            change,
            {"resources": [{"uid_ref": "res", "pam_settings": {"options": {"connections": "on"}}}]},
        )
        == []
    )


def test_preview_rotation_skips_empty_top_level_and_unresolvable_resources() -> None:
    """Covers commander_cli.py lines 2377, 2381-2382, 2386, 2390, 2393-2394, and 2408."""
    assert commander_cli_mod._preview_rotation_argvs_by_ref({}) == {}
    assert (
        commander_cli_mod._preview_rotation_argvs_by_ref(
            {
                "users": [
                    {
                        "uid_ref": "top-user",
                        "type": "pamUser",
                        "rotation_settings": {"enabled": "on"},
                    }
                ]
            }
        )
        == {}
    )
    assert (
        commander_cli_mod._preview_rotation_argvs_by_ref(
            {
                "pam_configurations": [{"uid_ref": "cfg1"}, {"uid_ref": "cfg2"}],
                "resources": [
                    "not-a-resource",
                    {"users": []},
                    {
                        "uid_ref": "res",
                        "title": "Resource",
                        "users": [
                            {
                                "uid_ref": "user",
                                "type": "pamUser",
                                "rotation_settings": {"enabled": "on"},
                            }
                        ],
                    },
                ],
            }
        )
        == {}
    )
    assert (
        commander_cli_mod._preview_rotation_argvs_by_ref(
            {
                "pam_configurations": [{"uid_ref": "cfg", "title": "Config"}],
                "resources": [
                    {
                        "uid_ref": "res",
                        "title": "Resource",
                        "users": [{"type": "pamUser", "rotation_settings": {"enabled": "on"}}],
                    }
                ],
            }
        )
        == {}
    )


def test_preview_ref_uses_title_and_unresolved_fallbacks() -> None:
    """Covers commander_cli.py lines 2425-2427."""
    assert commander_cli_mod._preview_ref(None, "Resource", role="resource") == (
        "<resource:Resource>"
    )
    assert commander_cli_mod._preview_ref(None, None, role="resource") == "<resource:unresolved>"


def test_manifest_source_and_resource_helpers_handle_models_and_non_mappings() -> None:
    """Covers commander_cli.py lines 2449-2450 and 2458."""

    class _DumpDict:
        def model_dump(self, **_kwargs: object) -> dict[str, object]:
            return {"resources": ["not-a-resource", {"uid_ref": "res", "title": "Resource"}]}

    class _DumpList:
        def model_dump(self, **_kwargs: object) -> list[str]:
            return ["not-a-dict"]

    source = commander_cli_mod._manifest_source_dict(_DumpDict())
    assert source == {"resources": ["not-a-resource", {"uid_ref": "res", "title": "Resource"}]}
    assert commander_cli_mod._manifest_source_dict(_DumpList()) == {}
    assert list(commander_cli_mod._manifest_resources_by_ref(source)) == ["res"]


def test_rotation_builder_skips_non_mapping_resources_and_requires_parent_identity() -> None:
    """Covers commander_cli.py lines 2560 and 2575."""
    assert build_pam_rotation_edit_argvs({"resources": ["not-a-resource"]}) == []

    with pytest.raises(ValueError, match="requires a parent resource with uid_ref and title"):
        build_pam_rotation_edit_argvs(
            {
                "pam_configurations": [{"uid_ref": "cfg", "title": "Config"}],
                "resources": [
                    {
                        "uid_ref": "res",
                        "users": [
                            {
                                "uid_ref": "user",
                                "title": "User",
                                "type": "pamUser",
                                "rotation_settings": {"enabled": "on"},
                            }
                        ],
                    }
                ],
            }
        )


def test_rotation_ref_resolver_uses_plan_title_match() -> None:
    """Covers commander_cli.py line 2657."""
    resolver = commander_cli_mod._RotationRefResolver(
        plan=Plan(
            manifest_name="Project",
            changes=[
                Change(
                    kind=ChangeKind.NOOP,
                    uid_ref=None,
                    resource_type="pamUser",
                    title="Admin",
                    keeper_uid="admin-uid",
                )
            ],
            order=[],
        ),
        live_records=[],
    )

    assert (
        resolver.resolve(
            uid_ref=None,
            title="Admin",
            resource_type="pamUser",
            role="admin",
        )
        == "admin-uid"
    )


def test_post_import_tuning_empty_connection_and_rbi_builders_noop() -> None:
    """Covers commander_cli.py lines 2742 and 2790."""
    assert build_post_import_tuning_argvs("record-uid", {"type": "pamMachine"}) == []
    assert build_post_import_tuning_argvs("record-uid", {"type": "pamRemoteBrowser"}) == []


def test_scalar_render_helpers_handle_string_and_non_collection_values() -> None:
    """Covers commander_cli.py lines 2803, 2811-2815, 2835, and 2847."""
    assert commander_cli_mod._on_off("custom") == "custom"
    assert commander_cli_mod._inverse_on_off("on") == "off"
    assert commander_cli_mod._inverse_on_off("off") == "on"
    assert commander_cli_mod._inverse_on_off("custom") == "custom"

    argv: list[str] = []
    commander_cli_mod._append_ref(argv, "--ref", 123, {})
    commander_cli_mod._append_ref(argv, "--ref", "", {})
    assert argv == []

    commander_cli_mod._append_repeated(argv, "--value", 42)
    assert argv == ["--value", "42"]


def test_manifest_rotation_config_identity_and_schedule_helpers() -> None:
    """Covers commander_cli.py lines 2881, 2917, 2939-2940, 2966, 2982, 2990-2993, and 3018."""
    with pytest.raises(ValueError, match="manifest data is required"):
        build_pam_rotation_edit_argvs(None)

    assert commander_cli_mod._has_nested_user_rotation({"resources": ["not-a-resource"]}) is False
    assert commander_cli_mod._rotation_config_ref(
        {"pam_configurations": [{"uid_ref": "cfg", "title": "Config"}]},
        {"uid_ref": "res"},
    ) == ("cfg", "Config")
    assert (
        commander_cli_mod._rotation_admin_uid(
            {},
            commander_cli_mod._RotationRefResolver(plan=None, live_records=[]),
            {},
        )
        is None
    )
    assert commander_cli_mod._desired_identity(
        {
            "resources": ["not-a-resource"],
            "users": [{"uid_ref": "admin", "type": "pamUser", "title": "Admin"}],
        },
        "admin",
    ) == ("pamUser", "Admin")
    assert commander_cli_mod._desired_identity(
        {"resources": ["not-a-resource"], "users": [{"uid_ref": "admin"}]},
        "missing",
    ) == (None, None)
    assert commander_cli_mod._rotation_schedule_args({"type": "cron"}) == []


def test_detect_unsupported_capabilities_handles_none_model_and_other_inputs() -> None:
    """Covers commander_cli.py lines 3075, 3077, and 3081."""

    class _VaultModel:
        def model_dump(self, **_kwargs: object) -> dict[str, str]:
            return {"schema": "keeper-vault.v1"}

    assert commander_cli_mod._detect_unsupported_capabilities(None) == []
    assert commander_cli_mod._detect_unsupported_capabilities(_VaultModel()) == []
    assert commander_cli_mod._detect_unsupported_capabilities("not-a-manifest") == []


def test_argv_value_returns_none_for_missing_and_trailing_flags() -> None:
    """Covers commander_cli.py lines 3131-3132 and 3134."""
    assert commander_cli_mod._argv_value(["cmd"], "--missing") is None
    assert commander_cli_mod._argv_value(["cmd", "--flag"], "--flag") is None
