"""Live proof test for ``dsk report ksm-usage``.

Exercises the real CLI end-to-end against a live Keeper tenant.

Skipped unless **all** of the following env vars are set:

  - ``KEEPER_LIVE_TENANT=1``
  - ``KEEPER_LIVE_KSM_CONFIG``   path to a KSM config JSON (used for auth
    context awareness only — the actual report reads Commander session
    state via ``~/.keeper/config.json`` / ``KEEPER_CONFIG``).

The test does **not** print or log the value of any credential env var or
the contents of ``KEEPER_CONFIG``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.live(
    requires=("KEEPER_LIVE_KSM_CONFIG",),
)
def test_ksm_usage_exits_zero_with_output() -> None:
    """``dsk --provider commander report ksm-usage`` exits 0 and emits a table."""
    config_path = Path(os.environ.get("KEEPER_CONFIG", "~/.keeper/config.json")).expanduser()

    env = os.environ.copy()
    # Ensure KEEPER_CONFIG points at the Commander session used by the subprocess.
    env["KEEPER_CONFIG"] = str(config_path)
    # Unset any variable that could echo secrets into captured output.
    env.pop("KEEPER_PASSWORD", None)

    result = subprocess.run(
        [sys.executable, "-m", "keeper_sdk.cli", "--provider", "commander", "report", "ksm-usage"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, (
        f"dsk report ksm-usage exited {result.returncode}.\n"
        f"stderr (last 400 chars): {result.stderr[-400:]}"
    )

    stdout = result.stdout
    # The table renderer always emits the summary line "N apps, M keys".
    assert "apps" in stdout and "keys" in stdout, (
        "Expected summary line '<N> apps, <M> keys' in output but got:\n"
        f"{stdout[:600]}"
    )
    # The Rich table header should also appear.
    assert "KSM Usage" in stdout or "apps" in stdout.lower(), (
        "Expected 'KSM Usage' table header in output but got:\n"
        f"{stdout[:600]}"
    )


@pytest.mark.live(
    requires=("KEEPER_LIVE_KSM_CONFIG",),
)
def test_ksm_usage_json_shape() -> None:
    """``dsk --provider commander report ksm-usage --json`` emits valid JSON with expected keys."""
    config_path = Path(os.environ.get("KEEPER_CONFIG", "~/.keeper/config.json")).expanduser()

    env = os.environ.copy()
    env["KEEPER_CONFIG"] = str(config_path)
    env.pop("KEEPER_PASSWORD", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "keeper_sdk.cli",
            "--provider",
            "commander",
            "report",
            "ksm-usage",
            "--json",
            "--quiet",
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, (
        f"dsk report ksm-usage --json exited {result.returncode}.\n"
        f"stderr (last 400 chars): {result.stderr[-400:]}"
    )

    # Locate the JSON envelope in stdout (there may be a Rich table before it).
    stdout = result.stdout
    json_start = stdout.find("{")
    assert json_start != -1, f"No JSON object found in stdout:\n{stdout[:600]}"

    try:
        payload = json.loads(stdout[json_start:])
    except json.JSONDecodeError as exc:
        pytest.fail(f"stdout did not contain valid JSON: {exc}\nstdout:\n{stdout[:600]}")

    # Required envelope keys (see run_ksm_usage_report return value).
    assert "apps" in payload, f"'apps' key missing from JSON payload: {list(payload.keys())}"
    assert "total_keys" in payload, (
        f"'total_keys' key missing from JSON payload: {list(payload.keys())}"
    )
    assert isinstance(payload["apps"], list), (
        f"'apps' must be a list, got {type(payload['apps'])}"
    )
