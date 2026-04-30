"""Regression tests for manifest-internal uid_ref enforcement."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_REF


def test_validate_rejects_cross_manifest_pam_configuration_uid_ref(invalid_manifest) -> None:
    """Cross-manifest config reuse is deferred; unresolved refs must fail at stage 3."""
    manifest_path: Path = invalid_manifest("missing-ref.yaml")

    result = CliRunner().invoke(main, ["validate", str(manifest_path)], catch_exceptions=False)

    assert result.exit_code == EXIT_REF
    assert "reference error:" in result.output
    assert "does-not-exist" in result.output
    assert "lonely-machine" in result.output
