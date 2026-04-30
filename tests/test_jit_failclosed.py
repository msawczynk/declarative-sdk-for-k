"""Fail-closed coverage for the JIT upstream-gap surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY, EXIT_CONFLICT
from keeper_sdk.providers.commander_cli import CommanderCliProvider


def _run(args: list[str]):
    runner = CliRunner()
    return runner.invoke(main, args, catch_exceptions=False)


@pytest.fixture
def commander_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSK_PREVIEW", "1")
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which",
        lambda _bin: "/usr/bin/keeper",
    )
    monkeypatch.setattr(CommanderCliProvider, "discover", lambda self: [])


def _write_jit_manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "jit.yaml"
    manifest_path.write_text(
        """
version: "1"
name: jit-upstream-gap
resources:
  - uid_ref: res.shell
    type: pamMachine
    title: shell
    host: shell.example.com
    pam_settings:
      options:
        jit_settings:
          create_ephemeral: true
          elevate: true
          elevation_method: group
          elevation_string: wheel
          ephemeral_account_type: linux
""".lstrip(),
        encoding="utf-8",
    )
    return manifest_path


def test_jit_design_declares_upstream_gap() -> None:
    text = Path("docs/JIT_DESIGN.md").read_text(encoding="utf-8")

    assert "Status: `upstream-gap`" in text
    assert "Do not wire an SDK JIT apply path" in text


def test_jit_plan_emits_conflict_with_upstream_gap_reason(
    commander_offline: None,
    tmp_path: Path,
) -> None:
    manifest_path = _write_jit_manifest(tmp_path)

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
    assert "jit_settings" in reason
    assert "not implemented" in reason


def test_jit_apply_exits_without_attempting_mutation(
    commander_offline: None,
    tmp_path: Path,
) -> None:
    manifest_path = _write_jit_manifest(tmp_path)

    result = _run(["--provider", "commander", "apply", str(manifest_path), "--auto-approve"])

    assert result.exit_code in {EXIT_CONFLICT, EXIT_CAPABILITY}, result.output
    combined = result.output + result.stderr
    assert "pam jit" in combined or "not implemented" in combined
