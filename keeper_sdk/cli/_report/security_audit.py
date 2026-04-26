"""`security-audit report` Commander wrapper."""

from __future__ import annotations

from typing import Any

import keeper_sdk.cli._report.runner as keeper_runner
from keeper_sdk.cli._report.common import (
    build_envelope,
    fingerprint_uid_fields,
    parse_report_json_array,
)
from keeper_sdk.core.redact import redact


def run_security_audit_report(
    *,
    nodes: tuple[str, ...],
    record_details: bool,
    breachwatch: bool,
    score_type: str,
    force: bool,
    quiet: bool,
    keeper_bin: str | None = None,
    config_file: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """Run ``keeper security-audit report --format json``."""
    argv = ["security-audit", "report", "--format", "json"]
    for n in nodes:
        argv += ["--node", n]
    if record_details:
        argv.append("--record-details")
    if breachwatch:
        argv.append("--breachwatch")
    argv += ["--score-type", score_type]
    if force:
        argv.append("--force")
    raw = keeper_runner.run_keeper_batch(
        argv, keeper_bin=keeper_bin, config_file=config_file, password=password
    )
    rows = parse_report_json_array(raw, command="security-audit report")
    fp_keys: tuple[str, ...] = ("record_uid",) if record_details else ()
    if quiet and fp_keys:
        rows = fingerprint_uid_fields(rows, fp_keys)
    sanitized_rows: list[Any] = redact(rows)  # type: ignore[assignment]
    return build_envelope(
        command="security-audit-report",
        rows=sanitized_rows,
        meta={
            "nodes": list(nodes),
            "record_details": record_details,
            "breachwatch": breachwatch,
            "score_type": score_type,
            "force": force,
            "quiet": quiet,
        },
    )
