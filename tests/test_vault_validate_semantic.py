"""Vault semantic validation coverage."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from keeper_sdk.cli import main


def test_validate_vault_rejects_duplicate_field_labels(tmp_path: Path) -> None:
    path = tmp_path / "vault-duplicate-labels.yaml"
    path.write_text(
        """
schema: keeper-vault.v1
records:
  - uid_ref: vault.login.dup
    type: login
    title: Dup Label Login
    fields:
      - type: login
        label: Account
        value: ["alice@example.com"]
      - type: text
        label: Account
        value: ["prod"]
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["validate", str(path)], catch_exceptions=False)

    assert result.exit_code == 2
    assert (
        "record 'Dup Label Login': duplicate field labels: Account. Rename fields to unique labels."
    ) in result.output
