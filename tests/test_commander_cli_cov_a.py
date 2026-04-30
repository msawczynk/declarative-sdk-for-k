"""Coverage slice for CommanderCliProvider lines 100-620."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.planner import Plan
from keeper_sdk.providers import commander_cli as commander_cli_mod
from keeper_sdk.providers.commander_cli import (
    CommanderCliProvider,
    _dict_items,
    _ensure_keepercommander_version_for_apply,
    _keepercommander_installed_tuple,
    _manifest_source_is_vault,
    _semver_tuple_at_least,
)


def _provider(
    monkeypatch: pytest.MonkeyPatch,
    *,
    folder_uid: str | None = "folder-uid",
    manifest_source: dict[str, Any] | None = None,
) -> CommanderCliProvider:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    return CommanderCliProvider(folder_uid=folder_uid, manifest_source=manifest_source)


def _create_plan(*, uid_ref: str = "res.db", title: str = "db-prod") -> Plan:
    return Plan(
        manifest_name="customer-prod",
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref=uid_ref,
                resource_type="pamDatabase",
                title=title,
                after={"title": title},
            )
        ],
        order=[uid_ref],
    )


def test_semver_tuple_accepts_installed_greater_component() -> None:
    """covers L100 (semver short-circuits when installed component is greater)."""
    assert _semver_tuple_at_least((17, 3), (17, 2, 13)) is True


def test_keepercommander_installed_tuple_missing_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L111-L112 (missing keepercommander package returns empty tuple)."""

    def missing_version(_name: str) -> str:
        raise importlib_metadata.PackageNotFoundError

    monkeypatch.setattr(importlib_metadata, "version", missing_version)

    assert _keepercommander_installed_tuple() == ()


def test_keepercommander_installed_tuple_stops_at_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L120 (non-digit suffix stops parsing current version segment)."""
    monkeypatch.setattr(importlib_metadata, "version", lambda _name: "17.2.13rc1")

    assert _keepercommander_installed_tuple() == (17, 2, 13)


def test_keepercommander_installed_tuple_stops_at_empty_segment_digits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L122 (segment with no leading digits stops version parsing)."""
    monkeypatch.setattr(importlib_metadata, "version", lambda _name: "17.2.dev1")

    assert _keepercommander_installed_tuple() == (17, 2)


def test_dict_items_rejects_non_list() -> None:
    """covers L133 (non-list payload becomes empty dict-item list)."""
    assert _dict_items({"not": "a-list"}) == []


def test_ensure_keepercommander_version_rejects_missing_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L140 (apply version gate rejects absent keepercommander package)."""
    monkeypatch.setattr(commander_cli_mod, "_keepercommander_installed_tuple", lambda: ())

    with pytest.raises(CapabilityError) as exc_info:
        _ensure_keepercommander_version_for_apply()

    assert "not installed" in exc_info.value.reason


def test_manifest_source_is_vault_rejects_none() -> None:
    """covers L163 (None manifest source is not a vault manifest)."""
    assert _manifest_source_is_vault(None) is False


def test_manifest_source_is_vault_uses_model_dump() -> None:
    """covers L165 (typed manifest source is read through model_dump)."""

    class VaultSource:
        def model_dump(self, *, mode: str, exclude_none: bool, by_alias: bool) -> dict[str, str]:
            assert mode == "python"
            assert exclude_none is True
            assert by_alias is True
            return {"schema": "keeper-vault.v1"}

    assert _manifest_source_is_vault(VaultSource()) is True


def test_manifest_source_is_vault_rejects_opaque_source() -> None:
    """covers L169 (opaque non-dict source is not a vault manifest)."""
    assert _manifest_source_is_vault(object()) is False


def test_provider_init_rejects_missing_keeper_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """covers L205 (constructor raises when keeper CLI is unavailable)."""
    monkeypatch.setattr("keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: None)

    with pytest.raises(CapabilityError) as exc_info:
        CommanderCliProvider(folder_uid="folder-uid")

    assert "keeper CLI not found" in exc_info.value.reason


def test_manifest_has_resource_entries_rejects_non_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L214 (non-dict manifest source cannot declare resources)."""
    provider = _provider(monkeypatch)
    provider._manifest_source = ["not", "a", "dict"]  # type: ignore[assignment]

    assert provider._manifest_has_resource_entries() is False


def test_discover_rejects_non_array_ls_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """covers L238 (discover rejects non-array `ls --format json` output)."""
    provider = _provider(monkeypatch)
    monkeypatch.setattr(provider, "_run_cmd", lambda _args: "{}")

    with pytest.raises(CapabilityError) as exc_info:
        provider.discover()

    assert "non-array JSON" in exc_info.value.reason


def test_discover_skips_record_listing_without_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    """covers L246 (record listing without uid is ignored before `get`)."""
    provider = _provider(monkeypatch)
    calls: list[list[str]] = []

    def fake_run(args: list[str]) -> str:
        calls.append(args)
        assert args[:1] == ["ls"]
        return json.dumps([{"type": "record", "title": "missing uid"}])

    monkeypatch.setattr(provider, "_run_cmd", fake_run)

    assert provider.discover() == []
    assert calls == [["ls", "folder-uid", "--format", "json"]]


def test_discover_rejects_non_object_get_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """covers L256 (discover rejects non-object `get --format json` output)."""
    provider = _provider(monkeypatch)

    def fake_run(args: list[str]) -> str:
        if args[:1] == ["ls"]:
            return json.dumps([{"type": "record", "uid": "REC1"}])
        if args[:1] == ["get"]:
            return "[]"
        raise AssertionError(f"unexpected args: {args}")

    monkeypatch.setattr(provider, "_run_cmd", fake_run)

    with pytest.raises(CapabilityError) as exc_info:
        provider.discover()

    assert "non-object JSON" in exc_info.value.reason


def test_discover_calls_enrichment_when_keeper_params_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L274 (cached KeeperParams triggers RBI DAG enrichment hook)."""
    provider = _provider(monkeypatch)
    provider._keeper_params = object()
    seen: list[list[LiveRecord]] = []

    monkeypatch.setattr(provider, "_run_cmd", lambda _args: "[]")
    monkeypatch.setattr(provider, "_enrich_pam_remote_browser_dag_options", seen.append)

    assert provider.discover() == []
    assert seen == [[]]


def test_resolve_pam_configuration_keeper_uid_all_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L281-L303 (RBI config uid_ref resolution branches)."""
    provider = _provider(
        monkeypatch,
        manifest_source={
            "resources": [
                {"uid_ref": "res.browser", "pam_configuration_uid_ref": "cfg.browser"},
                {"uid_ref": "res.blank", "pam_configuration_uid_ref": "  "},
            ]
        },
    )
    config = LiveRecord(
        keeper_uid="CFG_UID",
        title="Browser Config",
        resource_type="pam_configuration",
        marker={"uid_ref": "cfg.browser"},
    )

    assert (
        provider._resolve_pam_configuration_keeper_uid(
            LiveRecord(
                keeper_uid="RBI_UID",
                title="Browser",
                resource_type="pamRemoteBrowser",
                marker={"uid_ref": "res.browser"},
            ),
            [config],
        )
        == "CFG_UID"
    )
    assert (
        provider._resolve_pam_configuration_keeper_uid(
            LiveRecord(
                keeper_uid="RBI_UID",
                title="Browser",
                resource_type="pamRemoteBrowser",
                marker={},
            ),
            [config],
        )
        is None
    )

    provider._manifest_source = ["not", "a", "dict"]  # type: ignore[assignment]
    assert (
        provider._resolve_pam_configuration_keeper_uid(
            LiveRecord(
                keeper_uid="RBI_UID",
                title="Browser",
                resource_type="pamRemoteBrowser",
                marker={"uid_ref": "res.browser"},
            ),
            [config],
        )
        is None
    )

    provider._manifest_source = {"resources": [{"uid_ref": "res.browser"}]}
    assert (
        provider._resolve_pam_configuration_keeper_uid(
            LiveRecord(
                keeper_uid="RBI_UID",
                title="Browser",
                resource_type="pamRemoteBrowser",
                marker={"uid_ref": "res.browser"},
            ),
            [config],
        )
        is None
    )

    provider._manifest_source = {
        "resources": [{"uid_ref": "res.browser", "pam_configuration_uid_ref": "cfg.missing"}]
    }
    assert (
        provider._resolve_pam_configuration_keeper_uid(
            LiveRecord(
                keeper_uid="RBI_UID",
                title="Browser",
                resource_type="pamRemoteBrowser",
                marker={"uid_ref": "res.browser"},
            ),
            [config],
        )
        is None
    )


def test_enrich_pam_remote_browser_dag_options_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L318-L355 (TunnelDAG import, cache, skip, and merge paths)."""
    provider = _provider(monkeypatch)
    records = [
        LiveRecord(keeper_uid="MACHINE_UID", title="Machine", resource_type="pamMachine"),
    ]

    monkeypatch.setitem(
        sys.modules,
        "keepercommander.commands.tunnel.port_forward.tunnel_helpers",
        None,
    )
    provider._enrich_pam_remote_browser_dag_options(records)

    for name in [
        "keepercommander",
        "keepercommander.commands",
        "keepercommander.commands.tunnel",
        "keepercommander.commands.tunnel.port_forward",
    ]:
        module = types.ModuleType(name)
        setattr(module, "__path__", [])
        monkeypatch.setitem(sys.modules, name, module)

    helper_module = types.ModuleType("keepercommander.commands.tunnel.port_forward.tunnel_helpers")
    helper_module.get_keeper_tokens = lambda _params: ("session", "transmission", "key")  # type: ignore[attr-defined]
    graph_module = types.ModuleType("keepercommander.commands.tunnel.port_forward.TunnelGraph")
    created_cfg_uids: list[str] = []

    class FakeLinkingDag:
        def __init__(self, has_graph: bool) -> None:
            self.has_graph = has_graph

    class FakeTunnelDAG:
        def __init__(
            self,
            _params: object,
            _encrypted_session_token: str,
            _encrypted_transmission_key: str,
            cfg_uid: str,
            *,
            transmission_key: str,
        ) -> None:
            assert transmission_key == "key"
            created_cfg_uids.append(cfg_uid)
            self.linking_dag = FakeLinkingDag(cfg_uid != "CFG_OFF")

        def get_resource_setting(self, rid: str, _group: str, setting: str) -> str | None:
            values = {
                ("RBI_UID", "connections"): "on",
                ("RBI_UID", "sessionRecording"): "off",
            }
            return values.get((rid, setting))

    graph_module.TunnelDAG = FakeTunnelDAG  # type: ignore[attr-defined]
    monkeypatch.setitem(
        sys.modules,
        "keepercommander.commands.tunnel.port_forward.tunnel_helpers",
        helper_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "keepercommander.commands.tunnel.port_forward.TunnelGraph",
        graph_module,
    )

    provider._keeper_params = None
    provider._enrich_pam_remote_browser_dag_options(records)

    provider._keeper_params = object()
    provider._manifest_source = {
        "resources": [
            {"uid_ref": "res.off", "pam_configuration_uid_ref": "cfg.off"},
            {"uid_ref": "res.browser", "pam_configuration_uid_ref": "cfg.browser"},
        ]
    }
    off_record = LiveRecord(
        keeper_uid="RBI_OFF",
        title="Off",
        resource_type="pamRemoteBrowser",
        marker={"uid_ref": "res.off"},
    )
    browser_record = LiveRecord(
        keeper_uid="RBI_UID",
        title="Browser",
        resource_type="pamRemoteBrowser",
        marker={"uid_ref": "res.browser"},
        payload={},
    )
    provider._enrich_pam_remote_browser_dag_options(
        [
            LiveRecord(keeper_uid="OTHER_UID", title="Other", resource_type="pamMachine"),
            LiveRecord(
                keeper_uid="RBI_MISSING",
                title="Missing",
                resource_type="pamRemoteBrowser",
                marker={"uid_ref": "res.missing"},
            ),
            LiveRecord(
                keeper_uid="CFG_OFF",
                title="Off Config",
                resource_type="pam_configuration",
                marker={"uid_ref": "cfg.off"},
            ),
            off_record,
            LiveRecord(
                keeper_uid="CFG_UID",
                title="Browser Config",
                resource_type="pam_configuration",
                marker={"uid_ref": "cfg.browser"},
            ),
            browser_record,
        ]
    )

    assert created_cfg_uids == ["CFG_OFF", "CFG_UID"]
    assert browser_record.payload["pam_settings"]["options"] == {
        "remote_browser_isolation": "on",
        "graphical_session_recording": "off",
    }


def test_check_tenant_bindings_accepts_none_manifest_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L402 (None manifest source yields no online binding rows)."""
    provider = _provider(monkeypatch)
    provider._manifest_source = None  # type: ignore[assignment]

    assert provider.check_tenant_bindings() == []


def test_check_tenant_bindings_reads_dict_source_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L404-L407 (attr, dict, and opaque manifest source list readers)."""
    provider = _provider(monkeypatch, manifest_source={"gateways": [], "pam_configurations": []})

    assert provider.check_tenant_bindings() == []

    class Source:
        gateways: list[object] = []
        pam_configurations: list[object] = []

    assert provider.check_tenant_bindings(Source()) == []
    provider._manifest_source = ["opaque"]  # type: ignore[assignment]
    assert provider.check_tenant_bindings() == []


def test_check_tenant_bindings_get_rejects_opaque_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L416-L418 (binding item getter returns None for opaque objects)."""

    class CreateGateway:
        mode = "create"
        name = "Ignored"
        uid_ref = "gw.ignored"

    provider = _provider(monkeypatch, manifest_source={"gateways": [CreateGateway(), object()]})
    monkeypatch.setattr(provider, "_pam_gateway_rows", lambda: [])
    monkeypatch.setattr(provider, "_pam_config_rows", lambda: [])

    issues = provider.check_tenant_bindings()

    assert issues == [
        "gateway '' (uid_ref=) not found on tenant; "
        "check the enterprise's `pam gateway list --format json` output"
    ]


def test_check_tenant_bindings_reports_gateway_list_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L425-L426 (gateway listing failure becomes binding issue)."""
    provider = _provider(monkeypatch, manifest_source={"gateways": [{"name": "GW"}]})

    def fail_gateways() -> list[dict[str, str]]:
        raise OSError("gateway boom")

    monkeypatch.setattr(provider, "_pam_gateway_rows", fail_gateways)

    assert provider.check_tenant_bindings() == ["could not list tenant gateways: gateway boom"]


def test_check_tenant_bindings_reports_config_list_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L429-L430 (PAM configuration listing failure becomes binding issue)."""
    provider = _provider(
        monkeypatch,
        manifest_source={"pam_configurations": [{"uid_ref": "cfg", "title": "Config"}]},
    )
    monkeypatch.setattr(provider, "_pam_gateway_rows", lambda: [])

    def fail_configs() -> list[dict[str, str]]:
        raise CapabilityError(reason="config boom")

    monkeypatch.setattr(provider, "_pam_config_rows", fail_configs)

    assert provider.check_tenant_bindings() == [
        "could not list tenant PAM configurations: config boom."
    ]


def test_check_tenant_bindings_skips_config_without_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L474 (PAM configuration without title is skipped)."""
    provider = _provider(
        monkeypatch,
        manifest_source={"pam_configurations": [{"uid_ref": "cfg.missing-title"}]},
    )
    monkeypatch.setattr(provider, "_pam_gateway_rows", lambda: [])
    monkeypatch.setattr(provider, "_pam_config_rows", lambda: [])

    assert provider.check_tenant_bindings() == []


def test_check_tenant_bindings_reports_gateway_app_mismatch_and_unverified_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L455-L465 (gateway app mismatch and unverifiable binding issue)."""
    provider = _provider(
        monkeypatch,
        manifest_source={
            "gateways": [
                {
                    "uid_ref": "gw.mismatch",
                    "name": "Mismatch GW",
                    "ksm_application_name": "Declared App",
                },
                {
                    "uid_ref": "gw.unverified",
                    "name": "Unverified GW",
                    "ksm_application_name": "Declared App",
                },
            ]
        },
    )
    monkeypatch.setattr(
        provider,
        "_pam_gateway_rows",
        lambda: [
            {
                "gateway_name": "Mismatch GW",
                "gateway_uid": "GW_MISMATCH",
                "app_title": "Actual App",
                "app_uid": "APP_ACTUAL",
            },
            {
                "gateway_name": "Unverified GW",
                "gateway_uid": "GW_UNVERIFIED",
                "app_title": "",
                "app_uid": "",
            },
        ],
    )
    monkeypatch.setattr(provider, "_pam_config_rows", lambda: [])
    monkeypatch.setattr(
        provider,
        "_gateway_bound_app_name",
        lambda row: (
            ("Actual App", None)
            if row["gateway_name"] == "Mismatch GW"
            else (None, "missing app name")
        ),
    )

    assert provider.check_tenant_bindings() == [
        "gateway 'Mismatch GW' declares ksm_application_name='Declared App' "
        "but tenant has it bound to 'Actual App'",
        "gateway 'Unverified GW' declares ksm_application_name='Declared App' "
        "but the tenant binding could not be verified: missing app name",
    ]


def test_check_tenant_bindings_reports_config_binding_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L475-L496 (config missing, shared-folder missing, gateway mismatch)."""
    provider = _provider(
        monkeypatch,
        manifest_source={
            "gateways": [{"uid_ref": "gw.expected", "name": "Expected GW"}],
            "pam_configurations": [
                {"uid_ref": "cfg.missing", "title": "Missing Config"},
                {"uid_ref": "cfg.no-sf", "title": "No Shared Folder"},
                {
                    "uid_ref": "cfg.mismatch",
                    "title": "Gateway Mismatch",
                    "gateway_uid_ref": "gw.expected",
                },
            ],
        },
    )
    monkeypatch.setattr(
        provider,
        "_pam_gateway_rows",
        lambda: [{"gateway_name": "Expected GW", "gateway_uid": "GW_EXPECTED"}],
    )
    monkeypatch.setattr(
        provider,
        "_pam_config_rows",
        lambda: [
            {
                "config_name": "No Shared Folder",
                "config_uid": "CFG_NO_SF",
                "gateway_uid": "GW_EXPECTED",
                "shared_folder_uid": "",
            },
            {
                "config_name": "Gateway Mismatch",
                "config_uid": "CFG_MISMATCH",
                "gateway_uid": "GW_ACTUAL",
                "shared_folder_uid": "SF_UID",
            },
        ],
    )

    issues = provider.check_tenant_bindings()

    assert issues[0] == (
        "pam_configuration 'Missing Config' (uid_ref=cfg.missing) not found on tenant; "
        "declare a matching title or create the configuration in Keeper first"
    )
    assert "pam_configuration 'No Shared Folder' has no shared_folder on tenant" in issues[1]
    assert issues[2] == (
        "pam_configuration 'Gateway Mismatch' declares gateway_uid_ref='gw.expected' "
        "(uid=GW_EXPECTED) but tenant pairs it with gateway uid 'GW_ACTUAL'"
    )


def test_apply_reference_existing_dry_run_uses_extend_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L563 (reference-existing dry-run rewrites extend folder paths)."""
    provider = _provider(
        monkeypatch,
        manifest_source={
            "version": "1",
            "name": "customer-prod",
            "gateways": [{"uid_ref": "gw", "name": "GW", "mode": "reference_existing"}],
            "pam_configurations": [{"uid_ref": "cfg", "title": "Config"}],
            "resources": [{"uid_ref": "res.db", "type": "pamDatabase", "title": "db-prod"}],
        },
    )
    monkeypatch.setattr(
        commander_cli_mod, "_ensure_keepercommander_version_for_apply", lambda: None
    )
    monkeypatch.setattr(
        commander_cli_mod,
        "to_pam_import_json",
        lambda _manifest: {
            "pam_configuration": {"title": "Config", "gateway_name": "GW"},
            "pam_data": {
                "resources": [{"title": "db-prod", "users": [{"username": "db-user"}]}],
                "users": [{"username": "top-user"}],
            },
        },
    )
    monkeypatch.setattr(
        provider,
        "_resolve_reference_configuration",
        lambda _payload: {
            "gateway_name": "GW",
            "gateway_uid": "GW_UID",
            "app_uid": "APP_UID",
            "config_uid": "CFG_UID",
            "config_name": "Config",
        },
    )
    calls: list[list[str]] = []
    written_payloads: list[dict[str, Any]] = []

    def fake_run(args: list[str]) -> str:
        calls.append(args)
        assert args[:6] == ["pam", "project", "extend", "--config", "Config", "--file"]
        written_payloads.append(json.loads(Path(args[6]).read_text()))
        return ""

    monkeypatch.setattr(provider, "_run_cmd", fake_run)

    outcomes = provider.apply_plan(_create_plan(), dry_run=True)

    assert calls[0][-1] == "--dry-run"
    assert written_payloads == [
        {
            "pam_data": {
                "resources": [
                    {
                        "title": "db-prod",
                        "users": [
                            {
                                "username": "db-user",
                                "folder_path": "customer-prod - Users",
                            }
                        ],
                        "folder_path": "customer-prod - Resources",
                    }
                ],
                "users": [{"username": "top-user", "folder_path": "customer-prod - Users"}],
            }
        }
    ]
    assert outcomes[0].details == {"dry_run": True}


def test_apply_wraps_discover_failure_after_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """covers L619-L620 (post-import discover failure preserves partial outcomes)."""
    provider = _provider(
        monkeypatch,
        manifest_source={
            "version": "1",
            "name": "customer-prod",
            "resources": [{"uid_ref": "res.db", "type": "pamDatabase", "title": "db-prod"}],
        },
    )
    monkeypatch.setattr(
        commander_cli_mod, "_ensure_keepercommander_version_for_apply", lambda: None
    )
    monkeypatch.setattr(
        commander_cli_mod,
        "to_pam_import_json",
        lambda _manifest: {"project": "customer-prod", "pam_data": {"resources": []}},
    )
    monkeypatch.setattr(provider, "_run_cmd", lambda _args: "")
    monkeypatch.setattr(provider, "_resolve_project_resources_folder", lambda _name: "folder-uid")

    def fail_discover() -> list[LiveRecord]:
        raise CapabilityError(
            reason="discover boom",
            next_action="inspect tenant",
            context={"stage": "discover"},
        )

    monkeypatch.setattr(provider, "discover", fail_discover)

    with pytest.raises(CapabilityError) as exc_info:
        provider.apply_plan(_create_plan())

    assert exc_info.value.reason == "discover() after pam import/extend failed: discover boom"
    assert exc_info.value.next_action == "inspect tenant"
    assert exc_info.value.context["stage"] == "discover"
    partial = exc_info.value.context["partial_outcomes"]
    assert len(partial) == 1
    assert partial[0].uid_ref == "res.db"
