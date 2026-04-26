"""`password-report` Commander wrapper."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from typing import Any

from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.redact import redact


def _run_keeper_batch(
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


def _fingerprint_uid(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"<uid:{digest}>"


def _fingerprint_record_uids_in_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            out.append(row)
            continue
        copy = dict(row)
        uid = copy.get("record_uid")
        if isinstance(uid, str) and uid:
            copy["record_uid"] = _fingerprint_uid(uid)
        out.append(copy)
    return out


def run_password_report(
    *,
    policy: str,
    folder: str | None,
    verbose: bool,
    quiet: bool,
    keeper_bin: str | None = None,
    config_file: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """Run Commander ``password-report --format json`` and return a DSK envelope.

    Commander emits a JSON array of row objects (see ``dump_report_data``).
    ``quiet`` replaces ``record_uid`` values with short fingerprints.
    """
    argv = ["password-report", "--format", "json", "--policy", policy]
    if verbose:
        argv.append("--verbose")
    if folder:
        argv.append(folder)
    raw = _run_keeper_batch(argv, keeper_bin=keeper_bin, config_file=config_file, password=password)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CapabilityError(
            reason=f"password-report returned non-JSON stdout: {exc}",
            context={"head": raw[:400]},
            next_action="run `keeper password-report --format json` manually and inspect output",
        ) from exc
    if not isinstance(parsed, list):
        raise CapabilityError(
            reason="password-report JSON was not an array",
            context={"sample": str(parsed)[:200]},
            next_action="upgrade keepercommander / Commander CLI to a compatible version",
        )
    rows: list[dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, dict):
            rows.append(item)
        else:
            rows.append({"value": item})
    if quiet:
        rows = _fingerprint_record_uids_in_rows(rows)
    sanitized_rows: list[dict[str, Any]] | list[Any] = redact(rows)  # type: ignore[assignment]
    return {
        "dsk_report_version": 1,
        "command": "password-report",
        "meta": {"policy": policy, "folder": folder or "", "verbose": verbose, "quiet": quiet},
        "rows": sanitized_rows,
    }
