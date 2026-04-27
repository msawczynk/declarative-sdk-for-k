"""Offline checks for `scripts/daybook/harness.sh` (no ~/.cursor-daybook-sync required for help/print-env)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="bash harness (Unix / GitHub Actions ubuntu)"
)

_REPO = Path(__file__).resolve().parent.parent
_HARNESS = _REPO / "scripts" / "daybook" / "harness.sh"


def _run_harness(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **(env or {})}
    # Force missing daybook clone: help and print-env must still succeed.
    env["DAYBOOK_SYNC_ROOT"] = "/__nonexistent_daybook__for_harness_test__"
    return subprocess.run(
        ["bash", str(_HARNESS), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_harness_help_exits_zero_without_daybook_sync() -> None:
    p = _run_harness("help")
    assert p.returncode == 0, p.stderr
    assert "dsk daybook harness" in p.stdout
    assert "boot" in p.stdout


def test_harness_print_env_exits_zero_without_daybook_sync() -> None:
    p = _run_harness("print-env")
    assert p.returncode == 0, p.stderr
    assert "JOURNAL_PATH" in p.stdout
    assert "LESSONS_PATH" in p.stdout
    assert "DAYBOOK_REPO" in p.stdout


def test_harness_boot_fails_cleanly_without_daybook_sync() -> None:
    p = _run_harness("boot")
    assert p.returncode == 1
    assert "missing directory" in p.stderr or "missing directory" in p.stdout


def test_harness_boot_hints_when_sync_root_is_scripts_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scripts = Path(tmp) / "scripts"
        scripts.mkdir()
        (scripts / "agent_session_boot.sh").write_text("# stub\n", encoding="utf-8")
        env = {**os.environ, "DAYBOOK_SYNC_ROOT": str(scripts)}
        p = subprocess.run(
            ["bash", str(_HARNESS), "boot"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    assert p.returncode == 1
    err = p.stderr + p.stdout
    assert "clone root" in err
    assert "scripts/" in err
