"""Offline coverage for ``dsk run`` and enterprise report delegation."""

from __future__ import annotations

import json
import subprocess

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main


def _run(args: list[str]):
    runner = CliRunner()
    return runner.invoke(main, args, catch_exceptions=False)


def _install_fake_passthrough(
    monkeypatch: pytest.MonkeyPatch,
    result: subprocess.CompletedProcess[str],
    calls: list[list[str]] | None = None,
) -> None:
    def fake_run_keeper_passthrough(argv: list[str], **_kwargs: object):
        if calls is not None:
            calls.append(argv)
        return result

    monkeypatch.setattr(
        "keeper_sdk.cli._report.runner.run_keeper_passthrough",
        fake_run_keeper_passthrough,
    )


def _install_fake_enterprise_info(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[dict[str, object]],
) -> None:
    def fake_run_keeper_batch(_argv: list[str], **_kwargs: object) -> str:
        return json.dumps(rows)

    monkeypatch.setattr(
        "keeper_sdk.cli._report.runner.run_keeper_batch",
        fake_run_keeper_batch,
    )


def test_dsk_run_with_mock_provider_exits_capability_error() -> None:
    result = _run(["run", "pam", "gateway", "list"])

    assert result.exit_code == 5
    assert "requires --provider commander" in result.output
    assert "mock provider has no Commander session" in result.output


def test_dsk_run_invokes_commander_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    _install_fake_passthrough(
        monkeypatch,
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr=""),
        calls,
    )

    result = _run(["--provider", "commander", "run", "pam", "gateway", "list"])

    assert result.exit_code == 0
    assert result.output == "ok\n"
    assert calls == [["pam", "gateway", "list"]]


def test_dsk_run_accepts_quoted_command_string(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    _install_fake_passthrough(
        monkeypatch,
        subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        calls,
    )

    result = _run(["--provider", "commander", "run", "pam gateway list"])

    assert result.exit_code == 0
    assert calls == [["pam", "gateway", "list"]]


def test_dsk_run_json_option_appends_json_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    _install_fake_passthrough(
        monkeypatch,
        subprocess.CompletedProcess(args=[], returncode=0, stdout="[]", stderr=""),
        calls,
    )

    result = _run(["--provider", "commander", "run", "--json", "pam", "gateway", "list"])

    assert result.exit_code == 0
    assert calls == [["pam", "gateway", "list", "--json"]]


def test_dsk_run_exit_code_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_passthrough(
        monkeypatch,
        subprocess.CompletedProcess(args=[], returncode=7, stdout="bad\n", stderr=""),
    )

    result = _run(["--provider", "commander", "run", "bad-command"])

    assert result.exit_code == 7
    assert "bad" in result.output


def test_dsk_run_sanitize_uids_fingerprints_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    uid = "AbCdEfGhIjKlMnOpQrStUv"
    _install_fake_passthrough(
        monkeypatch,
        subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=f"record_uid={uid}\n",
            stderr="",
        ),
    )

    result = _run(["--provider", "commander", "run", "--sanitize-uids", "get", uid])

    assert result.exit_code == 0
    assert uid not in result.output
    assert "<uid:" in result.output


def test_dsk_run_redacts_secret_json_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_passthrough(
        monkeypatch,
        subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"title":"svc","password":"plain-secret"}',
            stderr="",
        ),
    )

    result = _run(["--provider", "commander", "run", "record", "get"])

    assert result.exit_code == 0
    assert "plain-secret" not in result.output
    assert "***redacted***" in result.output


def test_dsk_run_redacts_stderr_too(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_passthrough(
        monkeypatch,
        subprocess.CompletedProcess(
            args=[],
            returncode=2,
            stdout="",
            stderr="KEEPER_PASSWORD=swordfish\n",
        ),
    )

    result = _run(["--provider", "commander", "run", "bad"])

    assert result.exit_code == 2
    assert "swordfish" not in result.output
    assert "KEEPER_PASSWORD=***" in result.output


def test_report_team_report_invokes_enterprise_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_enterprise_info(
        monkeypatch,
        [{"team_uid": "TEAMUID01234567890123", "name": "Platform"}],
    )

    result = _run(["report", "team-report"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["command"] == "team-report"
    assert payload["rows"][0]["name"] == "Platform"


def test_report_role_report_invokes_enterprise_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_enterprise_info(
        monkeypatch,
        [{"role_id": 101, "name": "Admin"}],
    )

    result = _run(["report", "role-report"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["command"] == "role-report"
    assert payload["rows"][0]["name"] == "Admin"
