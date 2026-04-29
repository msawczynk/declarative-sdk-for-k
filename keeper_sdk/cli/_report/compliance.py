"""`compliance report` Commander wrapper (alias ``compliance-report``)."""

from __future__ import annotations

from typing import Any

import keeper_sdk.cli._report.runner as keeper_runner
from keeper_sdk.cli._report.common import (
    build_envelope,
    parse_report_json_array,
    prepare_report_rows,
)
from keeper_sdk.core.errors import CapabilityError

_COMMAND = "compliance report"


def _build_compliance_report_argv(
    *,
    node: str | None,
    username: tuple[str, ...],
    team: tuple[str, ...],
    rebuild: bool,
    no_cache: bool,
) -> list[str]:
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
    return argv


def _argv_with_rebuild(argv: list[str]) -> list[str]:
    if "--rebuild" in argv:
        return list(argv)
    rebuilt = list(argv)
    rebuilt.append("--rebuild")
    return rebuilt


def _run_compliance_rows(
    argv: list[str],
    *,
    keeper_bin: str | None,
    config_file: str | None,
    password: str | None,
) -> list[dict[str, Any]]:
    raw = keeper_runner.run_keeper_batch(
        argv, keeper_bin=keeper_bin, config_file=config_file, password=password
    )
    raw = keeper_runner.extract_json_array_stdout(raw)
    return parse_report_json_array(raw, command=_COMMAND)


def _run_compliance_rows_with_cache_rebuild_fallback(
    argv: list[str],
    *,
    rebuild: bool,
    keeper_bin: str | None,
    config_file: str | None,
    password: str | None,
) -> list[dict[str, Any]]:
    try:
        rows = _run_compliance_rows(
            argv, keeper_bin=keeper_bin, config_file=config_file, password=password
        )
    except CapabilityError:
        if rebuild:
            raise
        return _run_compliance_rows(
            _argv_with_rebuild(argv),
            keeper_bin=keeper_bin,
            config_file=config_file,
            password=password,
        )
    if rebuild or rows:
        return rows
    return _run_compliance_rows(
        _argv_with_rebuild(argv),
        keeper_bin=keeper_bin,
        config_file=config_file,
        password=password,
    )


def run_compliance_report(
    *,
    node: str | None,
    username: tuple[str, ...],
    team: tuple[str, ...],
    rebuild: bool,
    no_cache: bool,
    quiet: bool,
    sanitize_uids: bool,
    keeper_bin: str | None = None,
    config_file: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """Run ``keeper compliance report --format json`` (default enterprise report)."""
    argv = _build_compliance_report_argv(
        node=node,
        username=username,
        team=team,
        rebuild=rebuild,
        no_cache=no_cache,
    )
    rows = _run_compliance_rows_with_cache_rebuild_fallback(
        argv,
        rebuild=rebuild,
        keeper_bin=keeper_bin,
        config_file=config_file,
        password=password,
    )
    sanitized_rows = prepare_report_rows(
        rows,
        sanitize_uids=sanitize_uids,
        quiet=quiet,
        fingerprint_keys=("record_uid",),
    )
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
            "sanitize_uids": sanitize_uids,
        },
    )
