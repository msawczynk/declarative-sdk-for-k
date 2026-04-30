"""`compliance report` Commander wrapper (alias ``compliance-report``)."""

from __future__ import annotations

import json
from typing import Any

import keeper_sdk.cli._report.runner as keeper_runner
from keeper_sdk.cli._report.common import (
    build_envelope,
    parse_report_json_array,
    prepare_report_rows,
)
from keeper_sdk.core.errors import CapabilityError

_COMMAND = "compliance report"
COMPLIANCE_CACHE_EMPTY_WARNING = "compliance cache empty; re-run with --rebuild to populate"
_CACHE_EMPTY_CODE = "cache_empty"


class _ComplianceCacheEmpty(Exception):
    """Commander returned the known empty-cache compliance shape."""


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


def _is_empty_compliance_payload(raw: str) -> bool:
    text = (raw or "").strip()
    if not text:
        return True
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return False
    if parsed is None or parsed == [] or parsed == {}:
        return True
    if isinstance(parsed, dict):
        nodes = parsed.get("nodes")
        return isinstance(nodes, list) and not nodes
    return False


def _is_empty_cache_capability_error(exc: CapabilityError) -> bool:
    text = " ".join(
        str(part)
        for part in (
            exc.reason,
            exc.next_action,
            exc.context.get("stdout"),
            exc.context.get("stderr"),
            exc.context.get("head"),
        )
        if part
    ).casefold()
    if "compliance" not in text:
        return False
    return "cache" in text and ("empty" in text or "rebuild" in text)


def _run_compliance_rows(
    argv: list[str],
    *,
    empty_cache_is_warning: bool,
    keeper_bin: str | None,
    config_file: str | None,
    password: str | None,
) -> list[dict[str, Any]]:
    raw = keeper_runner.run_keeper_batch(
        argv, keeper_bin=keeper_bin, config_file=config_file, password=password
    )
    raw = keeper_runner.extract_json_array_stdout(raw)
    if empty_cache_is_warning and _is_empty_compliance_payload(raw):
        raise _ComplianceCacheEmpty
    return parse_report_json_array(raw, command=_COMMAND)


def _run_compliance_rows_or_empty_cache(
    argv: list[str],
    *,
    rebuild: bool,
    no_fail_on_empty: bool,
    keeper_bin: str | None,
    config_file: str | None,
    password: str | None,
) -> list[dict[str, Any]]:
    try:
        return _run_compliance_rows(
            argv,
            empty_cache_is_warning=not rebuild,
            keeper_bin=keeper_bin,
            config_file=config_file,
            password=password,
        )
    except _ComplianceCacheEmpty as exc:
        if rebuild or not no_fail_on_empty:
            raise CapabilityError(
                reason=COMPLIANCE_CACHE_EMPTY_WARNING,
                next_action="run `dsk report compliance-report --rebuild`",
            ) from exc
        raise
    except CapabilityError as exc:
        if rebuild or not no_fail_on_empty or not _is_empty_cache_capability_error(exc):
            raise
        raise _ComplianceCacheEmpty from exc


def _empty_cache_envelope() -> dict[str, Any]:
    return {"nodes": [], "warning": _CACHE_EMPTY_CODE}


def run_compliance_report(
    *,
    node: str | None,
    username: tuple[str, ...],
    team: tuple[str, ...],
    rebuild: bool,
    no_cache: bool,
    quiet: bool,
    sanitize_uids: bool,
    no_fail_on_empty: bool = True,
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
    try:
        rows = _run_compliance_rows_or_empty_cache(
            argv,
            rebuild=rebuild,
            no_fail_on_empty=no_fail_on_empty,
            keeper_bin=keeper_bin,
            config_file=config_file,
            password=password,
        )
    except _ComplianceCacheEmpty:
        return _empty_cache_envelope()
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
            "no_fail_on_empty": no_fail_on_empty,
            "quiet": quiet,
            "sanitize_uids": sanitize_uids,
        },
    )
