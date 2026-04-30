from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli._report.vault_health import run_vault_health_report


def _run(args: list[str]):
    runner = CliRunner()
    return runner.invoke(main, args, catch_exceptions=False)


def _install_list_records(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[dict[str, Any]] | dict[str, Any],
    calls: list[list[str]] | None = None,
) -> None:
    def fake_run_keeper_batch(argv: list[str], **_kwargs: object) -> str:
        if calls is not None:
            calls.append(argv)
        return json.dumps(rows)

    monkeypatch.setattr("keeper_sdk.cli._report.runner.run_keeper_batch", fake_run_keeper_batch)


def _healthy_row(uid: str = "AaBbCcDdEeFfGgHhIiJjKk") -> dict[str, Any]:
    return {
        "record_uid": uid,
        "title": "healthy login",
        "type": "login",
        "fields": [{"type": "password", "value": ["correct horse battery staple"]}],
        "rotation_policy": {"name": "quarterly"},
        "modified": "2999-01-01T00:00:00Z",
    }


def test_vault_health_calls_list_records_and_reports_no_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    _install_list_records(
        monkeypatch,
        [
            _healthy_row("UIDHEALTHY000000000001"),
            {
                "record_uid": "UIDNOPASS000000000001",
                "title": "missing password",
                "type": "login",
                "fields": [{"type": "login", "value": ["svc@example.invalid"]}],
                "rotation_policy": {"name": "quarterly"},
                "modified": "2999-01-01T00:00:00Z",
            },
        ],
        calls,
    )

    result = _run(["report", "vault-health"])

    assert result.exit_code == 0, result.output
    assert calls == [["list-records", "--format", "json"]]
    payload = json.loads(result.output)
    assert payload["command"] == "vault-health"
    assert payload["summary"]["total_records"] == 2
    assert payload["summary"]["flagged_records"] == 1
    assert payload["summary"]["no_password"] == 1
    assert payload["records"][0]["issues"] == ["no_password"]


def test_vault_health_detects_weak_password_indicator_and_omits_password_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _healthy_row()
    row["weak_password"] = True
    _install_list_records(monkeypatch, [row])

    result = _run(["report", "vault-health"])

    assert result.exit_code == 0, result.output
    assert "correct horse battery staple" not in result.output
    payload = json.loads(result.output)
    assert payload["summary"]["weak_password"] == 1
    assert payload["records"][0]["issues"] == ["weak_password"]


def test_vault_health_flags_records_shared_above_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _healthy_row()
    row["shared_users"] = ["a@example.invalid", "b@example.invalid", "c@example.invalid"]
    _install_list_records(monkeypatch, [row])

    result = _run(["report", "vault-health", "--shared-threshold", "2"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["shared_over_threshold"] == 1
    assert payload["records"][0]["shared_user_count"] == 3
    assert payload["records"][0]["issues"] == ["shared_over_threshold"]


def test_vault_health_flags_missing_rotation_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _healthy_row()
    row.pop("rotation_policy")
    _install_list_records(monkeypatch, [row])

    result = _run(["report", "vault-health"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["no_rotation_policy"] == 1
    assert payload["records"][0]["issues"] == ["no_rotation_policy"]


def test_vault_health_flags_stale_records_with_fixed_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _healthy_row()
    row["modified"] = "2026-01-01T00:00:00Z"
    _install_list_records(monkeypatch, [row])

    payload = run_vault_health_report(
        shared_threshold=10,
        stale_days=90,
        quiet=False,
        sanitize_uids=False,
        now=datetime(2026, 4, 29, tzinfo=UTC),
    )

    assert payload["summary"]["stale"] == 1
    assert payload["records"][0]["issues"] == ["stale"]
    assert payload["records"][0]["modified_at"] == "2026-01-01T00:00:00Z"


def test_vault_health_accepts_object_wrapped_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _healthy_row()
    row["password_strength"] = "weak"
    _install_list_records(monkeypatch, {"records": [row]})

    result = _run(["report", "vault-health"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["weak_password"] == 1


def test_vault_health_quiet_fingerprints_record_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid = "ZzYyXxWwVvUuTtSsRrQqPp"
    row = _healthy_row(uid)
    row.pop("rotation_policy")
    _install_list_records(monkeypatch, [row])

    result = _run(["report", "vault-health", "--quiet"])

    assert result.exit_code == 0, result.output
    assert uid not in result.output
    payload = json.loads(result.output)
    assert payload["records"][0]["record_uid"].startswith("<uid:")


def test_report_help_lists_all_report_commands() -> None:
    result = _run(["report", "--help"])

    assert result.exit_code == 0, result.output
    for name in (
        "password-report",
        "compliance-report",
        "security-audit-report",
        "vault-health",
        "ksm-usage",
        "team-report",
        "role-report",
    ):
        assert name in result.output
    assert "Weak-password rows" in result.output
    assert "Vault posture findings" in result.output


def test_ksm_usage_default_mock_exits_clean() -> None:
    result = _run(["report", "ksm-usage"])

    assert result.exit_code == 0, result.output
    assert "KSM Usage" in result.output
    assert "0 apps, 0 keys" in result.output
