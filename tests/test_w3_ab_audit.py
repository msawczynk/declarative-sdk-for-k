"""W3-AB audit: record_types plan path, keeper_fill CapabilityError, UnsupportedFamilyError taxonomy."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from keeper_sdk.cli.main import EXIT_CAPABILITY, EXIT_CHANGES
from keeper_sdk.cli.main import main as cli
from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import CapabilityError, ManifestError, UnsupportedFamilyError
from keeper_sdk.providers.commander_cli import CommanderCliProvider, _is_keeper_fill_change

# Mirrors tests/test_vault_diff_record_types.py::_record_type with uid_ref rt.svc-login.
VAULT_WITH_RECORD_TYPE_YAML = """\
schema: keeper-vault.v1
records: []
record_types:
  - uid_ref: rt.svc-login
    scope: enterprise
    record_type_id: 3000001
    content:
      $id: serviceLogin
      categories: [login]
      description: w3ab
      fields:
        - $ref: login
          required: true
        - $ref: password
          required: true
"""

UNSUPPORTED_PLAN_YAML = """\
schema: keeper-enterprise.v1
"""


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_plan_vault_with_record_types_emits_add_row(tmp_path: Path) -> None:
    path = _write(tmp_path, "vault.yaml", VAULT_WITH_RECORD_TYPE_YAML)
    runner = CliRunner()
    result = runner.invoke(cli, ["--provider", "mock", "plan", str(path)], catch_exceptions=False)
    assert result.exit_code == EXIT_CHANGES
    out = f"{result.output}{result.stderr or ''}"
    assert "record_type" in out
    assert "serviceLogin" in out or "rt.svc-login" in out


def test_plan_vault_record_types_no_drift_clean(tmp_path: Path) -> None:
    """Mock discover yields no live_record_type_defs — desired record_types[] stay create rows."""
    path = _write(tmp_path, "vault.yaml", VAULT_WITH_RECORD_TYPE_YAML)
    runner = CliRunner()
    result = runner.invoke(cli, ["--provider", "mock", "plan", str(path)], catch_exceptions=False)
    assert result.exit_code == EXIT_CHANGES
    assert "create" in (result.output or "").lower()


def test_keeper_fill_create_raises_capability_error() -> None:
    provider = CommanderCliProvider.__new__(CommanderCliProvider)
    with pytest.raises(CapabilityError) as excinfo:
        provider._vault_apply_keeper_fill_create({"settings": []})
    text = str(excinfo.value)
    assert "keeper_fill" in text
    assert "Commander writer" in text


def test_keeper_fill_update_raises_capability_error() -> None:
    provider = CommanderCliProvider.__new__(CommanderCliProvider)
    with pytest.raises(CapabilityError) as excinfo:
        provider._vault_apply_keeper_fill_update("uid-fake", {"settings": []})
    assert "keeper_fill" in str(excinfo.value)


def test_is_keeper_fill_change_detection() -> None:
    def row(*, uid_ref: str = "r1", resource_type: str = "login", title: str = "t") -> Change:
        return Change(
            kind=ChangeKind.ADD,
            uid_ref=uid_ref,
            resource_type=resource_type,
            title=title,
        )

    assert _is_keeper_fill_change(row(resource_type="keeper_fill")) is True
    assert _is_keeper_fill_change(row(resource_type="keeper_fill_setting")) is True
    assert _is_keeper_fill_change(row(resource_type="login", uid_ref="keeper_fill:tenant")) is True
    assert (
        _is_keeper_fill_change(row(resource_type="login", uid_ref="keeper_fill:tenant:k")) is True
    )
    assert _is_keeper_fill_change(row(resource_type="login", uid_ref="r1")) is False


def test_plan_unsupported_family_exits_capability(tmp_path: Path) -> None:
    path = _write(tmp_path, "enterprise.yaml", UNSUPPORTED_PLAN_YAML)
    runner = CliRunner()
    result = runner.invoke(cli, ["--provider", "mock", "plan", str(path)], catch_exceptions=False)
    assert result.exit_code == EXIT_CAPABILITY, (
        f"expected EXIT_CAPABILITY (5) for unsupported family, got {result.exit_code}: "
        f"{result.output}{result.stderr or ''}"
    )
    out = f"{result.output}{result.stderr or ''}"
    assert "capability error" in out


def test_unsupported_family_error_class_is_manifest_error_subclass() -> None:
    assert issubclass(UnsupportedFamilyError, ManifestError)
