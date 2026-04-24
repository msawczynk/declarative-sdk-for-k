"""Stage-5 (tenant binding) validation tests.

Covers :meth:`CommanderCliProvider.check_tenant_bindings` plus the
CLI's ``validate --online`` integration. Each test stubs the two
``pam {gateway,config} list --format json`` round-trips instead of
talking to a real tenant.

Pinned against ``docs/VALIDATION_STAGES.md`` — any change to the
stage-5 exit code contract or remediation text should update both.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from keeper_sdk.providers.commander_cli import CommanderCliProvider
from keeper_sdk.providers.mock import MockProvider

# ---------------------------------------------------------------------------
# Test fixtures — minimal manifest-shaped objects that satisfy the
# attribute lookups inside ``check_tenant_bindings``. Using plain
# dataclasses keeps the blast radius small and avoids re-validating
# pydantic models on every test.


@dataclass
class _Gateway:
    uid_ref: str
    name: str
    mode: str = "reference_existing"
    ksm_application_name: str | None = None


@dataclass
class _PamConfig:
    uid_ref: str
    title: str | None = None
    gateway_uid_ref: str | None = None


@dataclass
class _Manifest:
    gateways: list[_Gateway]
    pam_configurations: list[_PamConfig]


def _provider_with_rows(
    monkeypatch: pytest.MonkeyPatch,
    *,
    gateway_rows: list[dict[str, str]],
    config_rows: list[dict[str, str]],
) -> CommanderCliProvider:
    provider = CommanderCliProvider()
    monkeypatch.setattr(CommanderCliProvider, "_pam_gateway_rows", lambda self: gateway_rows)
    monkeypatch.setattr(CommanderCliProvider, "_pam_config_rows", lambda self: config_rows)
    return provider


# ---------------------------------------------------------------------------
# Happy paths


def test_happy_path_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider_with_rows(
        monkeypatch,
        gateway_rows=[
            {
                "app_title": "Lab App",
                "app_uid": "A1",
                "gateway_name": "Lab GW",
                "gateway_uid": "G1",
            }
        ],
        config_rows=[
            {
                "config_uid": "C1",
                "config_name": "Lab Config",
                "gateway_uid": "G1",
                "shared_folder_title": "Lab Folder",
                "shared_folder_uid": "SF1",
            }
        ],
    )
    manifest = _Manifest(
        gateways=[_Gateway(uid_ref="gw-lab", name="Lab GW", ksm_application_name="Lab App")],
        pam_configurations=[
            _PamConfig(uid_ref="cfg-lab", title="Lab Config", gateway_uid_ref="gw-lab")
        ],
    )
    assert provider.check_tenant_bindings(manifest) == []


def test_empty_manifest_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """No gateways + no pam_configs means no round-trip and no issues."""
    called: list[str] = []

    def _boom(self: Any) -> list[dict[str, str]]:
        called.append("called")
        raise AssertionError("should not be called for empty manifest")

    monkeypatch.setattr(CommanderCliProvider, "_pam_gateway_rows", _boom)
    monkeypatch.setattr(CommanderCliProvider, "_pam_config_rows", _boom)
    provider = CommanderCliProvider()
    assert provider.check_tenant_bindings(_Manifest(gateways=[], pam_configurations=[])) == []
    assert called == []


def test_mock_provider_returns_empty() -> None:
    """Mock provider always returns [] (no tenant to bind against)."""
    assert MockProvider().check_tenant_bindings(None) == []


def test_create_mode_gateway_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """``mode: create`` gateways aren't expected to exist yet — skip the lookup."""
    provider = _provider_with_rows(
        monkeypatch,
        gateway_rows=[],
        config_rows=[],
    )
    manifest = _Manifest(
        gateways=[_Gateway(uid_ref="gw-new", name="New GW", mode="create")],
        pam_configurations=[],
    )
    assert provider.check_tenant_bindings(manifest) == []


# ---------------------------------------------------------------------------
# Failure modes — one per documented stage-5 violation


def test_missing_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider_with_rows(monkeypatch, gateway_rows=[], config_rows=[])
    manifest = _Manifest(
        gateways=[_Gateway(uid_ref="gw-x", name="Missing GW")],
        pam_configurations=[],
    )
    issues = provider.check_tenant_bindings(manifest)
    assert len(issues) == 1
    assert "Missing GW" in issues[0]
    assert "gw-x" in issues[0]


def test_missing_pam_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider_with_rows(monkeypatch, gateway_rows=[], config_rows=[])
    manifest = _Manifest(
        gateways=[],
        pam_configurations=[_PamConfig(uid_ref="cfg-x", title="Absent Config")],
    )
    issues = provider.check_tenant_bindings(manifest)
    assert len(issues) == 1
    assert "Absent Config" in issues[0]
    assert "cfg-x" in issues[0]


def test_config_missing_shared_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider_with_rows(
        monkeypatch,
        gateway_rows=[],
        config_rows=[
            {
                "config_uid": "C1",
                "config_name": "Orphan Config",
                "gateway_uid": "",
                "shared_folder_title": "",
                "shared_folder_uid": "",
            }
        ],
    )
    manifest = _Manifest(
        gateways=[],
        pam_configurations=[_PamConfig(uid_ref="cfg-o", title="Orphan Config")],
    )
    issues = provider.check_tenant_bindings(manifest)
    assert any("no shared_folder" in issue for issue in issues)


def test_gateway_pairing_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider_with_rows(
        monkeypatch,
        gateway_rows=[
            {"app_title": "", "app_uid": "", "gateway_name": "GW-A", "gateway_uid": "G-A"},
            {"app_title": "", "app_uid": "", "gateway_name": "GW-B", "gateway_uid": "G-B"},
        ],
        config_rows=[
            {
                "config_uid": "C1",
                "config_name": "Cfg",
                "gateway_uid": "G-B",
                "shared_folder_title": "SF",
                "shared_folder_uid": "SF-1",
            }
        ],
    )
    manifest = _Manifest(
        gateways=[
            _Gateway(uid_ref="gw-a", name="GW-A"),
            _Gateway(uid_ref="gw-b", name="GW-B"),
        ],
        pam_configurations=[
            _PamConfig(uid_ref="cfg", title="Cfg", gateway_uid_ref="gw-a"),
        ],
    )
    issues = provider.check_tenant_bindings(manifest)
    assert any("gateway_uid_ref='gw-a'" in issue and "G-B" in issue for issue in issues)


def test_ksm_app_name_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider_with_rows(
        monkeypatch,
        gateway_rows=[
            {
                "app_title": "Actual App",
                "app_uid": "A1",
                "gateway_name": "GW",
                "gateway_uid": "G1",
            }
        ],
        config_rows=[],
    )
    manifest = _Manifest(
        gateways=[_Gateway(uid_ref="gw", name="GW", ksm_application_name="Expected App")],
        pam_configurations=[],
    )
    issues = provider.check_tenant_bindings(manifest)
    assert any(
        "ksm_application_name='Expected App'" in issue and "Actual App" in issue for issue in issues
    )


def test_ksm_app_name_uses_cached_app_list_and_surfaces_unverifiable_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _Manifest(
        gateways=[_Gateway(uid_ref="gw", name="GW", ksm_application_name="Expected App")],
        pam_configurations=[],
    )

    provider = _provider_with_rows(
        monkeypatch,
        gateway_rows=[
            {
                "app_title": "",
                "app_uid": "A1",
                "gateway_name": "GW",
                "gateway_uid": "G1",
            }
        ],
        config_rows=[],
    )
    pass_calls: list[list[str]] = []

    def _pass_run_cmd(args: list[str]) -> str:
        pass_calls.append(args)
        assert args == ["secrets-manager", "app", "list", "--format", "json"]
        return json.dumps({"applications": [{"app_name": "Expected App", "app_uid": "A1"}]})

    monkeypatch.setattr(provider, "_run_cmd", _pass_run_cmd)
    assert provider.check_tenant_bindings(manifest) == []
    assert provider.check_tenant_bindings(manifest) == []
    assert pass_calls == [["secrets-manager", "app", "list", "--format", "json"]]

    fail_provider = _provider_with_rows(
        monkeypatch,
        gateway_rows=[
            {
                "app_title": "",
                "app_uid": "A1",
                "gateway_name": "GW",
                "gateway_uid": "G1",
            }
        ],
        config_rows=[],
    )

    def _fail_run_cmd(args: list[str]) -> str:
        assert args == ["secrets-manager", "app", "list", "--format", "json"]
        return json.dumps({"applications": []})

    monkeypatch.setattr(fail_provider, "_run_cmd", _fail_run_cmd)
    issues = fail_provider.check_tenant_bindings(manifest)
    assert len(issues) == 1
    assert "could not be verified" in issues[0]
    assert "next_action=confirm the gateway's bound KSM application in the Keeper UI" in issues[0]


def test_multiple_issues_accumulate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stage-5 reports EVERY issue, not just the first — operators want the
    full list so they can fix the tenant once, not N retries."""
    provider = _provider_with_rows(monkeypatch, gateway_rows=[], config_rows=[])
    manifest = _Manifest(
        gateways=[
            _Gateway(uid_ref="gw-1", name="GW-1"),
            _Gateway(uid_ref="gw-2", name="GW-2"),
        ],
        pam_configurations=[
            _PamConfig(uid_ref="cfg-1", title="Cfg-1"),
            _PamConfig(uid_ref="cfg-2", title="Cfg-2"),
        ],
    )
    issues = provider.check_tenant_bindings(manifest)
    assert len(issues) == 4


# ---------------------------------------------------------------------------
# CLI integration


def test_cli_validate_online_exits_capability_on_binding_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """``dsk validate --online`` must exit EXIT_CAPABILITY (=5) when
    ``check_tenant_bindings`` returns any issue, and stream the issues
    to stderr. Pinned to the contract in ``docs/VALIDATION_STAGES.md``."""
    from click.testing import CliRunner

    from keeper_sdk.cli.main import main
    from keeper_sdk.core.interfaces import LiveRecord
    from keeper_sdk.providers.mock import MockProvider

    manifest_path = tmp_path / "env.yaml"
    manifest_path.write_text(
        'version: "1"\n'
        "name: test-env\n"
        "gateways:\n"
        "  - uid_ref: gw-a\n"
        "    name: GW-A\n"
        "    mode: reference_existing\n"
        "pam_configurations:\n"
        "  - uid_ref: cfg-a\n"
        "    environment: local\n"
        "    title: Missing Config\n"
    )

    class _FakeProvider(MockProvider):
        def discover(self) -> list[LiveRecord]:
            return [
                LiveRecord(keeper_uid="gw-uid", title="GW-A", resource_type="gateway"),
            ]

        def check_tenant_bindings(self, manifest: object = None) -> list[str]:
            return ["pam_configuration 'Missing Config' not found on tenant; do the thing"]

    import sys

    # ``keeper_sdk.cli.__init__`` does ``from .main import main``, which
    # makes attribute access on the ``keeper_sdk.cli`` package return the
    # click Group instead of the submodule. Go through ``sys.modules`` to
    # reach the real module object for monkeypatching.
    cli_main_mod = sys.modules["keeper_sdk.cli.main"]
    monkeypatch.setattr(cli_main_mod, "_make_provider", lambda *args, **kwargs: _FakeProvider())

    runner = CliRunner()
    result = runner.invoke(main, ["validate", str(manifest_path), "--online"])
    assert result.exit_code == 5, result.output
    assert "stage 5: tenant binding failures" in result.output
    assert "Missing Config" in result.output
