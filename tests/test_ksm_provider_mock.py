"""keeper-ksm.v1 mock provider plan/apply path."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY, EXIT_CHANGES
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.ksm_diff import compute_ksm_diff
from keeper_sdk.core.ksm_graph import ksm_apply_order
from keeper_sdk.core.models_ksm import KsmManifestV1, load_ksm_manifest
from keeper_sdk.core.planner import Plan, build_plan
from keeper_sdk.providers import KsmMockProvider

cli_main_module = importlib.import_module("keeper_sdk.cli.main")

MANIFEST_NAME = "ksm"
APP_REF = "keeper-ksm:apps:app.api"
RECORD_REF = "keeper-vault:records:record.db"


def _run(args: list[str]):
    return CliRunner().invoke(main, args, catch_exceptions=False)


def _minimal_doc() -> dict[str, Any]:
    return {
        "schema": "keeper-ksm.v1",
        "apps": [{"uid_ref": "app.api", "name": "API Service"}],
    }


def _full_doc(*, token_expiry: str = "2026-12-31T00:00:00Z") -> dict[str, Any]:
    return {
        "schema": "keeper-ksm.v1",
        "apps": [
            {
                "uid_ref": "app.api",
                "name": "API Service",
                "scopes": ["records:read", "records:update"],
                "allowed_ips": ["198.51.100.10/32"],
            }
        ],
        "tokens": [
            {
                "uid_ref": "token.api.bootstrap",
                "name": "bootstrap",
                "app_uid_ref": APP_REF,
                "one_time": True,
                "expiry": token_expiry,
            }
        ],
        "record_shares": [
            {
                "record_uid_ref": RECORD_REF,
                "app_uid_ref": APP_REF,
                "editable": True,
            }
        ],
        "config_outputs": [
            {
                "app_uid_ref": APP_REF,
                "format": "json",
                "output_path": "/tmp/ksm-config.json",
            }
        ],
    }


def _manifest(document: dict[str, Any] | None = None) -> KsmManifestV1:
    return load_ksm_manifest(document or _full_doc())


def _plan(
    manifest: KsmManifestV1,
    provider: KsmMockProvider,
    *,
    allow_delete: bool = False,
) -> Plan:
    changes = compute_ksm_diff(
        manifest,
        provider.discover_ksm_state(),
        manifest_name=MANIFEST_NAME,
        allow_delete=allow_delete,
    )
    return build_plan(MANIFEST_NAME, changes, ksm_apply_order(manifest))


def _write_manifest(tmp_path: Path, document: dict[str, Any] | None = None) -> Path:
    path = tmp_path / "ksm.yaml"
    path.write_text(_to_yamlish(document or _full_doc()), encoding="utf-8")
    return path


def _to_yamlish(document: dict[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(document, sort_keys=False)


def test_discover_ksm_apps_fresh_provider_empty() -> None:
    assert KsmMockProvider(MANIFEST_NAME).discover_ksm_apps() == []


def test_plan_detects_new_app() -> None:
    manifest = _manifest(_minimal_doc())
    changes = compute_ksm_diff(
        manifest,
        KsmMockProvider(MANIFEST_NAME).discover_ksm_state(),
        manifest_name=MANIFEST_NAME,
    )

    app_change = next(change for change in changes if change.resource_type == "ksm_app")
    assert app_change.kind is ChangeKind.CREATE
    assert app_change.uid_ref == "app.api"


def test_plan_detects_token_change() -> None:
    provider = KsmMockProvider(MANIFEST_NAME)
    provider.seed_ksm_state(_full_doc(token_expiry="2026-01-01T00:00:00Z"))

    changes = compute_ksm_diff(_manifest(), provider.discover_ksm_state())
    token_change = next(change for change in changes if change.resource_type == "ksm_token")

    assert token_change.kind is ChangeKind.UPDATE
    assert token_change.before == {"expiry": "2026-01-01T00:00:00Z"}
    assert token_change.after == {"expiry": "2026-12-31T00:00:00Z"}


def test_plan_detects_removed_share_when_delete_allowed() -> None:
    provider = KsmMockProvider(MANIFEST_NAME)
    provider.seed_ksm_state(_full_doc())

    changes = compute_ksm_diff(
        _manifest(_minimal_doc()),
        provider.discover_ksm_state(),
        allow_delete=True,
    )
    share_delete = next(change for change in changes if change.resource_type == "ksm_record_share")

    assert share_delete.kind is ChangeKind.DELETE
    assert share_delete.before["record_uid_ref"] == RECORD_REF


def test_apply_ksm_plan_creates_app_and_marker() -> None:
    provider = KsmMockProvider(MANIFEST_NAME)
    plan = _plan(_manifest(_minimal_doc()), provider)

    outcomes = provider.apply_ksm_plan(plan)

    assert [outcome.action for outcome in outcomes] == ["create"]
    app = provider.discover_ksm_apps()[0]
    assert app["uid_ref"] == "app.api"
    marker = provider.ksm_markers()[app["keeper_uid"]]
    assert marker["uid_ref"] == "app.api"
    assert marker["manifest"] == MANIFEST_NAME
    assert marker["resource_type"] == "ksm_app"


def test_apply_ksm_plan_dry_run_does_not_write_marker() -> None:
    provider = KsmMockProvider(MANIFEST_NAME)
    plan = _plan(_manifest(_minimal_doc()), provider)

    outcomes = provider.apply_ksm_plan(plan, dry_run=True)

    assert outcomes[0].details == {"dry_run": True, "marker_written": False}
    assert provider.discover_ksm_apps() == []
    assert provider.ksm_markers() == {}


def test_apply_then_replan_is_noop() -> None:
    provider = KsmMockProvider(MANIFEST_NAME)
    manifest = _manifest()

    provider.apply_ksm_plan(_plan(manifest, provider))
    plan_after = _plan(manifest, provider)

    assert plan_after.is_clean
    assert {change.kind for change in plan_after.changes} == {ChangeKind.NOOP}


def test_update_token_preserves_keeper_uid_and_updates_marker() -> None:
    provider = KsmMockProvider(MANIFEST_NAME)
    provider.seed_ksm_state(_full_doc(token_expiry="2026-01-01T00:00:00Z"))
    token_before = provider.discover_ksm_state()["tokens"][0]

    outcomes = provider.apply_ksm_plan(_plan(_manifest(), provider))

    token_after = provider.discover_ksm_state()["tokens"][0]
    assert any(outcome.action == "update" for outcome in outcomes)
    assert token_after["keeper_uid"] == token_before["keeper_uid"]
    assert token_after["expiry"] == "2026-12-31T00:00:00Z"
    assert provider.ksm_markers()[token_after["keeper_uid"]]["resource_type"] == "ksm_token"


def test_delete_share_removes_state_and_marker() -> None:
    provider = KsmMockProvider(MANIFEST_NAME)
    provider.seed_ksm_state(_full_doc())
    share_uid = provider.discover_ksm_state()["record_shares"][0]["keeper_uid"]

    provider.apply_ksm_plan(_plan(_manifest(_minimal_doc()), provider, allow_delete=True))

    assert provider.discover_ksm_state()["record_shares"] == []
    assert share_uid not in provider.ksm_markers()


def test_cli_mock_plan_emits_json_changes(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _minimal_doc())

    result = _run(["--provider", "mock", "plan", str(path), "--json"])

    assert result.exit_code == EXIT_CHANGES, result.output
    payload = json.loads(result.output)
    assert payload["manifest_name"] == MANIFEST_NAME
    assert payload["summary"]["create"] == 1
    assert payload["changes"][0]["resource_type"] == "ksm_app"


def test_cli_apply_creates_app_then_replan_noop(tmp_path: Path, monkeypatch) -> None:
    path = _write_manifest(tmp_path)
    provider = KsmMockProvider(MANIFEST_NAME)
    monkeypatch.setattr(cli_main_module, "KsmMockProvider", lambda manifest_name: provider)

    applied = _run(["--provider", "mock", "apply", str(path), "--auto-approve"])
    replanned = _run(["--provider", "mock", "plan", str(path), "--json"])

    assert applied.exit_code == 0, applied.output
    assert "Apply results" in applied.output
    assert replanned.exit_code == 0, replanned.output
    assert json.loads(replanned.output)["summary"] == {
        "create": 0,
        "update": 0,
        "delete": 0,
        "conflict": 0,
        "noop": 4,
    }


def test_cli_apply_dry_run_does_not_write_markers(tmp_path: Path, monkeypatch) -> None:
    path = _write_manifest(tmp_path, _minimal_doc())
    provider = KsmMockProvider(MANIFEST_NAME)
    monkeypatch.setattr(cli_main_module, "KsmMockProvider", lambda manifest_name: provider)

    result = _run(["--provider", "mock", "apply", str(path), "--dry-run"])

    assert result.exit_code == EXIT_CHANGES, result.output
    assert provider.discover_ksm_apps() == []
    assert provider.ksm_markers() == {}


def test_commander_provider_without_discovery_exits_capability(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = _write_manifest(tmp_path, _minimal_doc())

    class MissingCommanderProvider:
        def discover_ksm_state(self) -> dict[str, list[dict[str, Any]]]:
            raise CapabilityError(
                reason="Commander KSM discovery unavailable",
                next_action="configure Commander before planning keeper-ksm.v1",
            )

    monkeypatch.setattr(
        cli_main_module, "_make_provider", lambda *args, **kwargs: MissingCommanderProvider()
    )
    result = _run(["--provider", "commander", "plan", str(path), "--json"])

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert "discovery failed: Commander KSM discovery unavailable" in result.output
