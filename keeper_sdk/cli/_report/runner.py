"""Subprocess invocation of ``keeper`` in batch mode (shared by report verbs)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

# Keep in sync with ``CommanderCliProvider`` session retry heuristics.
_SESSION_EXPIRED_CODE = "session_token_expired"


def extract_json_array_stdout(stdout: str) -> str:
    """Return the first JSON array embedded in Commander stdout, if present."""
    text = (stdout or "").strip()
    if not text:
        return ""
    if text.startswith("[") and text.endswith("]"):
        return text
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "[":
            continue
        try:
            parsed, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return text[index : index + end].strip()
    return text


def _is_retryable_keeper_session_text(stdout: str | None, stderr: str | None) -> bool:
    text = f"{stdout or ''}\n{stderr or ''}".casefold()
    return _SESSION_EXPIRED_CODE in text or ("session token" in text and "expired" in text)


def run_keeper_batch(
    argv: list[str],
    *,
    keeper_bin: str | None,
    config_file: str | None,
    password: str | None,
) -> str:
    """Run ``keeper --batch-mode … argv``; return stdout (trimmed).

    Mirrors ``CommanderCliProvider._run_cmd``: ``--batch-mode``, optional
    ``--config``, ``KEEPER_PASSWORD`` in env, ``stdin=DEVNULL``, and up to
    **two** attempts when stderr/stdout indicates a refreshable session error.
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
    result: subprocess.CompletedProcess[str] | None = None
    for attempt in range(2):
        result = subprocess.run(
            base + argv,
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            env=env,
        )
        if result.returncode == 0 or attempt == 1:
            break
        if not _is_retryable_keeper_session_text(result.stdout, result.stderr):
            break
    assert result is not None
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
