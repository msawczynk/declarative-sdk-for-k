"""Enterprise team/role reports backed by Commander ``enterprise-info``."""

from __future__ import annotations

from typing import Any

import keeper_sdk.cli._report.runner as keeper_runner
from keeper_sdk.cli._report.common import (
    build_envelope,
    parse_report_json_array,
    prepare_report_rows,
)

_TEAM_COLUMNS = (
    "restricts",
    "node",
    "user_count",
    "users",
    "queued_user_count",
    "queued_users",
    "role_count",
    "roles",
)
_ROLE_COLUMNS = (
    "visible_below",
    "default_role",
    "admin",
    "node",
    "user_count",
    "users",
    "team_count",
    "teams",
    "enforcement_count",
    "enforcements",
    "managed_node_count",
    "managed_nodes",
    "managed_nodes_permissions",
)
_TEAM_ROLE_TEAM_COLUMNS = ("node", "user_count", "users", "role_count", "roles")
_TEAM_ROLE_ROLE_COLUMNS = ("node", "user_count", "users", "team_count", "teams")


def _enterprise_info_rows(
    argv: list[str],
    *,
    command: str,
    keeper_bin: str | None,
    config_file: str | None,
    password: str | None,
) -> list[dict[str, Any]]:
    raw = keeper_runner.run_keeper_batch(
        argv, keeper_bin=keeper_bin, config_file=config_file, password=password
    )
    raw = keeper_runner.extract_json_array_stdout(raw)
    return parse_report_json_array(raw, command=command)


def _enterprise_info_argv(selector: str, columns: tuple[str, ...]) -> list[str]:
    return [
        "enterprise-info",
        selector,
        "-v",
        "--format",
        "json",
        "--columns",
        ",".join(columns),
    ]


def _team_rows(
    columns: tuple[str, ...],
    *,
    keeper_bin: str | None,
    config_file: str | None,
    password: str | None,
) -> list[dict[str, Any]]:
    return _enterprise_info_rows(
        _enterprise_info_argv("-t", columns),
        command="enterprise-info -t -v --format json",
        keeper_bin=keeper_bin,
        config_file=config_file,
        password=password,
    )


def _role_rows(
    columns: tuple[str, ...],
    *,
    keeper_bin: str | None,
    config_file: str | None,
    password: str | None,
) -> list[dict[str, Any]]:
    return _enterprise_info_rows(
        _enterprise_info_argv("-r", columns),
        command="enterprise-info -r -v --format json",
        keeper_bin=keeper_bin,
        config_file=config_file,
        password=password,
    )


def run_team_report(
    *,
    quiet: bool,
    sanitize_uids: bool,
    keeper_bin: str | None = None,
    config_file: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """Run ``keeper enterprise-info -t -v --format json``."""
    rows = _team_rows(
        _TEAM_COLUMNS,
        keeper_bin=keeper_bin,
        config_file=config_file,
        password=password,
    )
    sanitized_rows = prepare_report_rows(
        rows,
        sanitize_uids=sanitize_uids,
        quiet=quiet,
        fingerprint_keys=("team_uid",),
    )
    return build_envelope(
        command="team-report",
        rows=sanitized_rows,
        meta={
            "source": "enterprise-info",
            "selector": "teams",
            "columns": list(_TEAM_COLUMNS),
            "quiet": quiet,
            "sanitize_uids": sanitize_uids,
        },
    )


def run_role_report(
    *,
    quiet: bool,
    sanitize_uids: bool,
    keeper_bin: str | None = None,
    config_file: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """Run ``keeper enterprise-info -r -v --format json``."""
    rows = _role_rows(
        _ROLE_COLUMNS,
        keeper_bin=keeper_bin,
        config_file=config_file,
        password=password,
    )
    sanitized_rows = prepare_report_rows(
        rows,
        sanitize_uids=sanitize_uids,
        quiet=quiet,
        fingerprint_keys=("role_id",),
    )
    return build_envelope(
        command="role-report",
        rows=sanitized_rows,
        meta={
            "source": "enterprise-info",
            "selector": "roles",
            "columns": list(_ROLE_COLUMNS),
            "quiet": quiet,
            "sanitize_uids": sanitize_uids,
        },
    )


def run_team_roles_report(
    *,
    quiet: bool,
    sanitize_uids: bool,
    keeper_bin: str | None = None,
    config_file: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """Run team and role relationship views from ``enterprise-info``."""
    team_rows = _team_rows(
        _TEAM_ROLE_TEAM_COLUMNS,
        keeper_bin=keeper_bin,
        config_file=config_file,
        password=password,
    )
    role_rows = _role_rows(
        _TEAM_ROLE_ROLE_COLUMNS,
        keeper_bin=keeper_bin,
        config_file=config_file,
        password=password,
    )
    tagged_rows: list[dict[str, Any]] = [{"object_type": "team", **row} for row in team_rows] + [
        {"object_type": "role", **row} for row in role_rows
    ]
    sanitized_rows = prepare_report_rows(
        tagged_rows,
        sanitize_uids=sanitize_uids,
        quiet=quiet,
        fingerprint_keys=("team_uid", "role_id"),
    )
    return build_envelope(
        command="team-roles",
        rows=sanitized_rows,
        meta={
            "source": "enterprise-info",
            "selectors": ["teams", "roles"],
            "team_columns": list(_TEAM_ROLE_TEAM_COLUMNS),
            "role_columns": list(_TEAM_ROLE_ROLE_COLUMNS),
            "team_count": len(team_rows),
            "role_count": len(role_rows),
            "quiet": quiet,
            "sanitize_uids": sanitize_uids,
        },
    )
