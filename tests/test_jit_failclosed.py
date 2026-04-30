"""JIT import/extend support coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CHANGES
from keeper_sdk.core.manifest import load_manifest
from keeper_sdk.core.normalize import to_pam_import_json
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


def _write_jit_manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "jit.yaml"
    manifest_path.write_text(
        """
version: "1"
name: jit-project-import
resources:
  - uid_ref: dir.linux
    type: pamDirectory
    title: Linux Directory
    directory_type: ldap
    host: ldap.example.com
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
          pam_directory_uid_ref: dir.linux
""".lstrip(),
        encoding="utf-8",
    )
    return manifest_path


def test_jit_design_declares_supported_import_extend_path() -> None:
    text = Path("docs/JIT_DESIGN.md").read_text(encoding="utf-8")

    assert "Status: `supported`" in text
    assert "pam project import" in text
    assert "pam project extend" in text


def test_jit_plan_emits_resource_creates_without_capability_conflict(
    commander_offline: None,
    tmp_path: Path,
) -> None:
    manifest_path = _write_jit_manifest(tmp_path)

    result = _run(["--provider", "commander", "plan", str(manifest_path), "--json"])

    assert result.exit_code == EXIT_CHANGES, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["conflict"] == 0
    assert any(change["resource_type"] == "pamMachine" for change in payload["changes"])


def test_jit_pam_directory_uid_ref_maps_to_commander_import_key(tmp_path: Path) -> None:
    manifest_path = _write_jit_manifest(tmp_path)
    manifest = load_manifest(manifest_path)

    payload = to_pam_import_json(manifest.model_dump(mode="python", exclude_none=True))
    machine = next(row for row in payload["pam_data"]["resources"] if row["title"] == "shell")

    jit_settings = machine["pam_settings"]["options"]["jit_settings"]
    assert jit_settings["pam_directory_record"] == "Linux Directory"
    assert "pam_directory_uid_ref" not in jit_settings
