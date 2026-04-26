"""`password-report` Commander wrapper."""

from __future__ import annotations

from typing import Any

import keeper_sdk.cli._report.runner as keeper_runner
from keeper_sdk.cli._report.common import (
    build_envelope,
    fingerprint_uid_fields,
    parse_report_json_array,
)
from keeper_sdk.core.redact import redact


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
    """Run Commander ``password-report --format json`` and return a DSK envelope."""
    argv = ["password-report", "--format", "json", "--policy", policy]
    if verbose:
        argv.append("--verbose")
    if folder:
        argv.append(folder)
    raw = keeper_runner.run_keeper_batch(
        argv, keeper_bin=keeper_bin, config_file=config_file, password=password
    )
    rows = parse_report_json_array(raw, command="password-report")
    if quiet:
        rows = fingerprint_uid_fields(rows, ("record_uid",))
    sanitized_rows: list[Any] = redact(rows)  # type: ignore[assignment]
    return build_envelope(
        command="password-report",
        rows=sanitized_rows,
        meta={"policy": policy, "folder": folder or "", "verbose": verbose, "quiet": quiet},
    )
