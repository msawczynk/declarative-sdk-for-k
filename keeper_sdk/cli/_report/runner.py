"""Subprocess invocation of ``keeper`` in batch mode (shared by report verbs)."""

from __future__ import annotations

import os
import shutil
import subprocess


def run_keeper_batch(
    argv: list[str],
    *,
    keeper_bin: str | None,
    config_file: str | None,
    password: str | None,
) -> str:
    """Run ``keeper --batch-mode … argv``; return stdout (trimmed).

    Mirrors the subprocess discipline in ``CommanderCliProvider._run_cmd``:
    ``--batch-mode``, optional ``--config``, ``KEEPER_PASSWORD`` in env,
    ``stdin=DEVNULL``.
    """
    from keeper_sdk.core.errors import CapabilityError

    bin_name = keeper_bin or os.environ.get("KEEPER_BIN", "keeper")
    if not shutil.which(bin_name):
        raise CapabilityError(
            reason=f"keeper CLI not found on PATH (looked up '{bin_name}')",
            next_action="install Keeper Commander or set KEEPER_BIN",
        )
    base = [bin_name, "--batch-mode"]
    cfg = config_file or os.environ.get("KEEPER_CONFIG")
    if cfg:
        base += ["--config", cfg]
    env = os.environ.copy()
    pwd = password or os.environ.get("KEEPER_PASSWORD")
    if pwd:
        env["KEEPER_PASSWORD"] = pwd
    result = subprocess.run(
        base + argv,
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env=env,
    )
    if result.returncode != 0:
        raise CapabilityError(
            reason=f"keeper {' '.join(argv)} failed (rc={result.returncode})",
            context={
                "stdout": (result.stdout or "")[-6000:],
                "stderr": (result.stderr or "")[-4000:],
            },
            next_action="inspect Commander stderr; ensure session is logged in",
        )
    return (result.stdout or "").strip()
