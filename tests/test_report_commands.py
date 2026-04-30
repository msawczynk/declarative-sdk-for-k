"""Offline coverage for ``dsk report`` compliance/security audit commands."""

from __future__ import annotations

import json
from typing import Any

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY, EXIT_GENERIC
from keeper_sdk.core.errors import CapabilityError


def _run(args: list[str]):
    runner = CliRunner()
    return runner.invoke(main, args, catch_exceptions=False)


def _install_fake_report(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[dict[str, Any]],
    calls: list[list[str]] | None = None,
) -> None:
    def fake_run_keeper_batch(argv: list[str], **_kwargs: object) -> str:
        if calls is not None:
            calls.append(argv)
        return json.dumps(rows)

    monkeypatch.setattr("keeper_sdk.cli._report.runner.run_keeper_batch", fake_run_keeper_batch)


def _install_fake_report_raw(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[str | BaseException],
    calls: list[list[str]] | None = None,
) -> None:
    def fake_run_keeper_batch(argv: list[str], **_kwargs: object) -> str:
        if calls is not None:
            calls.append(argv)
        if not responses:
            raise AssertionError("no fake report response queued")
        response = responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr("keeper_sdk.cli._report.runner.run_keeper_batch", fake_run_keeper_batch)


def test_compliance_report_sanitize_uids_fingerprints_uid_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid = "AbCdEfGhIjKlMnOpQrStUv"
    _install_fake_report(
        monkeypatch,
        [{"record_uid": uid, "title": "row1", "note": f"created keeper://{uid}"}],
    )

    result = _run(["report", "compliance-report", "--sanitize-uids", "--no-fail-on-empty"])

    assert result.exit_code == 0, result.output
    assert uid not in result.output
    payload = json.loads(result.output)
    row = payload["rows"][0]
    assert payload["command"] == "compliance-report"
    assert payload["meta"]["sanitize_uids"] is True
    assert row["record_uid"].startswith("<uid:")
    assert row["note"].startswith("created keeper://<uid:")


def test_compliance_report_warns_after_empty_stdout_without_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    _install_fake_report_raw(
        monkeypatch,
        [""],
        calls,
    )

    result = _run(["report", "compliance-report", "--quiet"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {"nodes": [], "warning": "cache_empty"}
    assert "compliance cache empty; re-run with --rebuild to populate" in result.stderr
    assert len(calls) == 1
    assert "--rebuild" not in calls[0]


def test_compliance_report_warns_after_empty_json_array_without_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    _install_fake_report_raw(
        monkeypatch,
        ["[]"],
        calls,
    )

    result = _run(["report", "compliance-report", "--sanitize-uids"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {"nodes": [], "warning": "cache_empty"}
    assert "compliance cache empty; re-run with --rebuild to populate" in result.stderr
    assert len(calls) == 1
    assert "--rebuild" not in calls[0]


def test_compliance_report_warns_after_null_payload_without_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    _install_fake_report_raw(monkeypatch, ["null"], calls)

    result = _run(["report", "compliance-report", "--sanitize-uids", "--quiet"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {"nodes": [], "warning": "cache_empty"}
    assert "compliance cache empty; re-run with --rebuild to populate" in result.stderr
    assert len(calls) == 1
    assert "--rebuild" not in calls[0]


def test_compliance_report_warns_after_cache_empty_commander_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    _install_fake_report_raw(
        monkeypatch,
        [
            CapabilityError(
                reason="keeper compliance report failed (rc=1)",
                next_action="rebuild the compliance cache",
            ),
        ],
        calls,
    )

    result = _run(["report", "compliance-report"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {"nodes": [], "warning": "cache_empty"}
    assert "compliance cache empty; re-run with --rebuild to populate" in result.stderr
    assert len(calls) == 1
    assert "--rebuild" not in calls[0]


def test_compliance_report_rebuild_proceeds_with_empty_json_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    _install_fake_report_raw(monkeypatch, ["[]"], calls)

    result = _run(["report", "compliance-report", "--rebuild"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["command"] == "compliance-report"
    assert payload["rows"] == []
    assert payload["meta"]["rebuild"] is True
    assert payload["meta"]["no_fail_on_empty"] is True
    assert result.stderr == ""
    assert len(calls) == 1
    assert "--rebuild" in calls[0]


def test_compliance_report_fail_on_empty_exits_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    _install_fake_report_raw(monkeypatch, ["[]"], calls)

    result = _run(["report", "compliance-report", "--fail-on-empty"])

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert "compliance cache empty; re-run with --rebuild to populate" in result.output
    assert len(calls) == 1
    assert "--rebuild" not in calls[0]


def test_compliance_report_refuses_raw_uid_when_leak_check_flags_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid = "AaBbCcDdEeFfGgHhIiJjKk"
    _install_fake_report(monkeypatch, [{"record_uid": uid, "title": "raw uid row"}])

    def fake_secret_leak_check(text: str, **_kwargs: object) -> list[str]:
        if uid in text:
            return ["report leaks raw Keeper UID"]
        return []

    monkeypatch.setattr(
        "keeper_sdk.cli._report.common.secret_leak_check",
        fake_secret_leak_check,
    )

    result = _run(["report", "compliance-report"])

    assert result.exit_code == EXIT_GENERIC, result.output
    assert "output failed leak check" in result.output
    assert "raw Keeper UID" in result.output


def test_security_audit_report_sanitize_uids_and_quiet_exit_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid = "ZzYyXxWwVvUuTtSsRrQqPp"
    calls: list[list[str]] = []
    _install_fake_report(
        monkeypatch,
        [{"record_uid": uid, "email": "a@example.com", "details": f"record {uid}"}],
        calls,
    )

    result = _run(
        [
            "report",
            "security-audit-report",
            "--record-details",
            "--sanitize-uids",
            "--quiet",
        ]
    )

    assert result.exit_code == 0, result.output
    assert uid not in result.output
    payload = json.loads(result.output)
    row = payload["rows"][0]
    assert payload["command"] == "security-audit-report"
    assert payload["meta"]["sanitize_uids"] is True
    assert payload["meta"]["quiet"] is True
    assert row["record_uid"].startswith("<uid:")
    assert row["details"].startswith("record <uid:")
    assert calls[0][:4] == ["security-audit", "report", "--format", "json"]


def test_security_audit_report_record_details_flag_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    _install_fake_report(monkeypatch, [{"email": "b@example.com", "weak": 1}], calls)

    result = _run(["report", "security-audit-report", "--record-details"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["meta"]["record_details"] is True
    assert "--record-details" in calls[0]


def test_compliance_and_security_sanitized_outputs_have_no_leaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid = "LmNoPqRsTuVwXyZaBcDeFg"
    calls: list[list[str]] = []
    _install_fake_report(monkeypatch, [{"record_uid": uid, "message": f"uid={uid}"}], calls)

    compliance = _run(["report", "compliance-report", "--sanitize-uids"])
    security = _run(
        [
            "report",
            "security-audit-report",
            "--record-details",
            "--sanitize-uids",
            "--quiet",
        ]
    )

    assert compliance.exit_code == 0, compliance.output
    assert security.exit_code == 0, security.output
    assert uid not in compliance.output
    assert uid not in security.output
    assert len(calls) == 2
