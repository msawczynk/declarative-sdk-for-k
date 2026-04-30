"""Offline coverage for ``dsk report ksm-usage``."""

from __future__ import annotations

import importlib
import json
from typing import Any

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_GENERIC
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.providers import KsmMockProvider

cli_main_module = importlib.import_module("keeper_sdk.cli.main")

MANIFEST_NAME = "ksm-usage"
API_APP_UID = "AaBbCcDdEeFfGgHhIiJjKk"
WORKER_APP_UID = "ZzYyXxWwVvUuTtSsRrQqPp"


def _run(args: list[str]):
    return CliRunner().invoke(main, args, catch_exceptions=False)


def _seeded_provider() -> KsmMockProvider:
    provider = KsmMockProvider(MANIFEST_NAME)
    provider.seed_ksm_state(
        {
            "apps": [
                {
                    "uid_ref": "app.api",
                    "name": "API Service",
                    "keeper_uid": API_APP_UID,
                },
                {
                    "uid_ref": "app.worker",
                    "name": "Worker Service",
                    "keeper_uid": WORKER_APP_UID,
                },
            ],
            "tokens": [],
            "record_shares": [
                {
                    "app_uid_ref": "keeper-ksm:apps:app.api",
                    "record_uid_ref": "keeper-vault:records:record.db",
                    "editable": True,
                },
                {
                    "app_uid_ref": "keeper-ksm:apps:app.api",
                    "record_uid_ref": "keeper-vault:records:record.cache",
                    "editable": False,
                },
                {
                    "app_uid_ref": "keeper-ksm:apps:app.worker",
                    "record_uid_ref": "keeper-vault:records:record.queue",
                    "editable": False,
                },
            ],
            "config_outputs": [],
        }
    )
    return provider


def _install_provider(monkeypatch: pytest.MonkeyPatch, provider: KsmMockProvider) -> None:
    monkeypatch.setattr(cli_main_module, "KsmMockProvider", lambda _manifest_name: provider)


def test_ksm_usage_empty_mock_state_renders_empty_table() -> None:
    result = _run(["report", "ksm-usage"])

    assert result.exit_code == 0, result.output
    assert "KSM Usage" in result.output
    assert "Application" in result.output
    assert "0 apps, 0 keys" in result.output


def test_ksm_usage_table_shows_apps_and_key_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_provider(monkeypatch, _seeded_provider())

    result = _run(["report", "ksm-usage"])

    assert result.exit_code == 0, result.output
    assert "2 apps, 3 keys" in result.output
    api_line = next(line for line in result.output.splitlines() if "API Service" in line)
    worker_line = next(line for line in result.output.splitlines() if "Worker Service" in line)
    assert "2" in api_line
    assert "1" in worker_line


def test_ksm_usage_json_flag_emits_apps_and_total_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_provider(monkeypatch, _seeded_provider())

    result = _run(["report", "ksm-usage", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert set(payload) >= {"apps", "total_keys"}
    assert payload["total_keys"] == 3
    assert [app["name"] for app in payload["apps"]] == ["API Service", "Worker Service"]


def test_ksm_usage_sanitize_uids_fingerprints_app_uids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_provider(monkeypatch, _seeded_provider())

    result = _run(["report", "ksm-usage", "--json", "--sanitize-uids"])

    assert result.exit_code == 0, result.output
    assert API_APP_UID not in result.output
    assert WORKER_APP_UID not in result.output
    payload = json.loads(result.output)
    assert all(app["app_uid"].startswith("<uid:") for app in payload["apps"])


def test_ksm_usage_commander_ksm_unavailable_returns_empty_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_keeper_batch(_argv: list[str], **_kwargs: Any) -> str:
        raise CapabilityError(
            reason="Commander KSM discovery unavailable",
            next_action="configure Commander before live KSM usage discovery",
        )

    monkeypatch.setattr("keeper_sdk.cli._report.runner.run_keeper_batch", fake_run_keeper_batch)

    result = _run(["--provider", "commander", "report", "ksm-usage", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "apps": [],
        "total_keys": 0,
        "warning": "ksm_unavailable",
    }


def test_ksm_usage_unexpected_commander_error_exits_generic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_keeper_batch(_argv: list[str], **_kwargs: Any) -> str:
        raise RuntimeError("Commander transport broke")

    monkeypatch.setattr("keeper_sdk.cli._report.runner.run_keeper_batch", fake_run_keeper_batch)

    result = _run(["--provider", "commander", "report", "ksm-usage"])

    assert result.exit_code == EXIT_GENERIC, result.output
    assert "unexpected Commander error" in result.output
    assert "Commander transport broke" in result.output


def test_ksm_usage_quiet_json_fingerprints_app_uids_and_exits_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """dsk report ksm-usage --quiet --json → exit 0, fingerprinted app_uid values."""
    _install_provider(monkeypatch, _seeded_provider())

    result = _run(["report", "ksm-usage", "--quiet", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert set(payload) >= {"apps", "total_keys"}
    # All app_uid values must be fingerprinted, not raw UIDs
    for app in payload["apps"]:
        uid = app.get("app_uid")
        assert uid is None or uid.startswith("<uid:"), f"app_uid not fingerprinted: {uid}"
    # Raw UIDs must not appear in output
    assert API_APP_UID not in result.output
    assert WORKER_APP_UID not in result.output
    # Table must be suppressed when --quiet is set with --json
    assert "KSM Usage" not in result.output
