"""Fail-closed coverage for unproven RBI fields."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CONFLICT
from keeper_sdk.providers.commander_cli import CommanderCliProvider


def _run(args: list[str]):
    runner = CliRunner()
    return runner.invoke(main, args, catch_exceptions=False)


@pytest.fixture
def commander_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which",
        lambda _bin: "/usr/bin/keeper",
    )
    monkeypatch.setattr(CommanderCliProvider, "discover", lambda self: [])


def _write_rbi_gap_manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "rbi.yaml"
    manifest_path.write_text(
        """
version: "1"
name: rbi-upstream-gap
resources:
  - uid_ref: rbi.portal
    type: pamRemoteBrowser
    title: portal
    url: https://portal.example.com
    pam_settings:
      connection:
        protocol: http
        recording_include_keys: true
        disable_audio: true
        audio_channels: 2
        audio_bps: 16
        audio_sample_rate: 44100
""".lstrip(),
        encoding="utf-8",
    )
    return manifest_path


def test_rbi_unsupported_fields_plan_as_upstream_gap_conflict(
    commander_offline: None,
    tmp_path: Path,
) -> None:
    manifest_path = _write_rbi_gap_manifest(tmp_path)

    result = _run(["--provider", "commander", "plan", str(manifest_path), "--json"])

    assert result.exit_code == EXIT_CONFLICT, result.output
    payload = json.loads(result.output)
    conflicts = [
        change
        for change in payload["changes"]
        if change["kind"] == "conflict" and change["resource_type"] == "capability"
    ]
    assert len(conflicts) == 1
    reason = conflicts[0]["reason"]
    assert "upstream-gap" in reason
    assert "recording_include_keys" in reason
    assert "disable_audio" in reason
    assert "pam rbi" in reason


def test_rbi_unsupported_fields_emit_clear_message_without_crashing(
    commander_offline: None,
    tmp_path: Path,
) -> None:
    manifest_path = _write_rbi_gap_manifest(tmp_path)

    result = _run(["--provider", "commander", "plan", str(manifest_path), "--json"])

    assert result.exit_code == EXIT_CONFLICT, result.output
    assert "Traceback" not in result.output
    payload = json.loads(result.output)
    reason = payload["changes"][0]["reason"]
    assert "unsupported RBI field(s)" in reason
    assert "audio_sample_rate" in reason
