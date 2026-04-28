"""Sanity checks for in-repo phase-harness shell helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BUNDLE_SCRIPT = REPO / "scripts" / "phase_harness" / "bundle_unpushed_commits.sh"
GATES_SCRIPT = REPO / "scripts" / "phase_harness" / "run_local_gates.sh"


@pytest.mark.parametrize("path", [BUNDLE_SCRIPT, GATES_SCRIPT])
def test_phase_harness_script_bash_syntax(path: Path) -> None:
    assert path.is_file(), path
    proc = subprocess.run(
        ["bash", "-n", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"bash -n {path}:\n{proc.stderr or proc.stdout}"


def test_bundle_unpushed_commits_script_runs_helpfully_when_nothing_to_pack(tmp_path: Path) -> None:
    """When main is ahead of origin, the script must create a valid bundle (smoke)."""
    out = tmp_path / "b.bundle"
    proc = subprocess.run(
        ["bash", str(BUNDLE_SCRIPT), str(out)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    out_combined = proc.stdout + proc.stderr
    if "Nothing to bundle" in out_combined:
        pytest.skip("main is not ahead of origin in this clone")
    assert proc.returncode == 0, proc.stderr
    assert "git pull" in out_combined and "git push" in out_combined, out_combined
    assert out.is_file()
    v = subprocess.run(
        ["git", "bundle", "verify", str(out)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert v.returncode == 0, v.stderr
