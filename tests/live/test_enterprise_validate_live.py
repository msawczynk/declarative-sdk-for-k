"""Live proof test for ``keeper-enterprise.v1`` online validate.

Runs ``dsk --provider commander validate --online`` against the enterprise
teams/roles fixture and asserts exit 0.

Skipped unless **both** of the following conditions hold:

  - ``KEEPER_LIVE_TENANT=1`` in env.
  - ``KEEPER_CONFIG`` or ``~/.keeper/config.json`` is present (Commander
    session with enterprise-info access).

The test does **not** print or log any credential env var or the contents of
``KEEPER_CONFIG``.  Only the last 400 chars of stderr are surfaced on failure.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# Canonical fixture path (relative to repo root)
_FIXTURE = Path(__file__).parent.parent / "fixtures" / "examples" / "enterprise-teams" / "environment.yaml"


@pytest.mark.live(
    requires=(),  # auth via ~/.keeper/config.json; KEEPER_LIVE_TENANT=1 is the gate
)
def test_enterprise_validate_online_exits_zero() -> None:
    """``dsk --provider commander validate --online`` exits 0 for enterprise fixture.

    Proof shape expected on stdout::

        ok: keeper-enterprise.v1 (<N> uid_refs); online: <M> enterprise objects
    """
    assert _FIXTURE.exists(), f"Enterprise fixture missing: {_FIXTURE}"

    config_path = Path(os.environ.get("KEEPER_CONFIG", "~/.keeper/config.json")).expanduser()

    env = os.environ.copy()
    env["KEEPER_CONFIG"] = str(config_path)
    # Do not echo secrets into subprocess output.
    env.pop("KEEPER_PASSWORD", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "keeper_sdk.cli",
            "--provider",
            "commander",
            "validate",
            str(_FIXTURE),
            "--online",
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, (
        f"dsk --provider commander validate --online exited {result.returncode}.\n"
        f"stderr (last 400 chars): {result.stderr[-400:]}"
    )

    stdout = result.stdout + result.stderr  # CLI may write to either stream
    assert "keeper-enterprise.v1" in stdout, (
        f"Expected 'keeper-enterprise.v1' in output but got:\n{stdout[:600]}"
    )
    assert "online:" in stdout, (
        f"Expected 'online:' summary token in output but got:\n{stdout[:600]}"
    )
    assert "ok:" in stdout, (
        f"Expected 'ok:' prefix in output but got:\n{stdout[:600]}"
    )
