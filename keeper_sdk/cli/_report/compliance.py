"""`compliance report` Commander wrapper (alias ``compliance-report``)."""

from __future__ import annotations

from typing import Any

import keeper_sdk.cli._report.runner as keeper_runner
from keeper_sdk.cli._report.common import (
    build_envelope,
    fingerprint_uid_fields,
    parse_report_json_array,
)
from keeper_sdk.core.redact import redact


def run_compliance_report(
    *,
    node: str | None,
    username: tuple[str, ...],
    team: tuple[str, ...],
    rebuild: bool,
    no_cache: bool,
    quiet: bool,
    keeper_bin: str | None = None,
    config_file: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """Run ``keeper compliance report --format json`` (default enterprise report)."""
    argv = ["compliance", "report", "--format", "json"]
    if rebuild:
        argv.append("--rebuild")
    if no_cache:
        argv.append("--no-cache")
    if node:
        argv += ["--node", node]
    for u in username:
        argv += ["--username", u]
    for t in team:
        argv += ["--team", t]
    raw = keeper_runner.run_keeper_batch(
        argv, keeper_bin=keeper_bin, config_file=config_file, password=password
    )
    rows = parse_report_json_array(raw, command="compliance report")
    if quiet:
        rows = fingerprint_uid_fields(rows, ("record_uid",))
    sanitized_rows: list[Any] = redact(rows)  # type: ignore[assignment]
    return build_envelope(
        command="compliance-report",
        rows=sanitized_rows,
        meta={
            "node": node or "",
            "usernames": list(username),
            "teams": list(team),
            "rebuild": rebuild,
            "no_cache": no_cache,
            "quiet": quiet,
        },
    )
