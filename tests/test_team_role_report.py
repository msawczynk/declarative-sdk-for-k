"""Offline coverage for enterprise-info backed team/role reports."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli._live.transcript import secret_leak_check


def _run(args: list[str]):
    runner = CliRunner()
    return runner.invoke(main, args, catch_exceptions=False)


def _install_enterprise_info(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[list[dict[str, object]]],
    calls: list[list[str]] | None = None,
) -> None:
    queue = [json.dumps(response) for response in responses]

    def fake_run_keeper_batch(argv: list[str], **_kwargs: object) -> str:
        if calls is not None:
            calls.append(argv)
        if not queue:
            raise AssertionError("no fake enterprise-info response queued")
        return queue.pop(0)

    monkeypatch.setattr(
        "keeper_sdk.cli._report.runner.run_keeper_batch",
        fake_run_keeper_batch,
    )


def test_team_report_uses_enterprise_info_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    team_uid = "ZzYyXxWwVvUuTtSsRrQqPp"
    calls: list[list[str]] = []
    _install_enterprise_info(
        monkeypatch,
        [
            [
                {
                    "team_uid": team_uid,
                    "name": "Platform",
                    "node": "Root",
                    "user_count": 1,
                    "users": ["alice@example.com"],
                    "role_count": 1,
                    "roles": ["Admin"],
                }
            ]
        ],
        calls,
    )

    result = _run(["report", "team-report", "--quiet"])

    assert result.exit_code == 0, result.output
    assert team_uid not in result.output
    payload = json.loads(result.stdout)
    assert payload["command"] == "team-report"
    assert payload["meta"]["source"] == "enterprise-info"
    assert payload["rows"][0]["team_uid"].startswith("<uid:")
    assert payload["rows"][0]["roles"] == ["Admin"]
    assert calls == [
        [
            "enterprise-info",
            "-t",
            "-v",
            "--format",
            "json",
            "--columns",
            "restricts,node,user_count,users,queued_user_count,queued_users,role_count,roles",
        ]
    ]


def test_role_report_uses_enterprise_info_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    _install_enterprise_info(
        monkeypatch,
        [
            [
                {
                    "role_id": 123,
                    "name": "Admin",
                    "admin": True,
                    "node": "Root",
                    "user_count": 1,
                    "users": ["alice@example.com"],
                    "team_count": 1,
                    "teams": ["Platform"],
                }
            ]
        ],
        calls,
    )

    result = _run(["report", "role-report"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["command"] == "role-report"
    assert payload["rows"][0]["role_id"] == 123
    assert payload["rows"][0]["teams"] == ["Platform"]
    assert calls == [
        [
            "enterprise-info",
            "-r",
            "-v",
            "--format",
            "json",
            "--columns",
            (
                "visible_below,default_role,admin,node,user_count,users,team_count,teams,"
                "enforcement_count,enforcements,managed_node_count,managed_nodes,"
                "managed_nodes_permissions"
            ),
        ]
    ]


def test_team_roles_report_combines_relationship_views_and_stays_leak_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KEEPER_PASSWORD", "plain-secret")
    monkeypatch.setenv("KEEPER_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    calls: list[list[str]] = []
    _install_enterprise_info(
        monkeypatch,
        [
            [
                {
                    "team_uid": "ZzYyXxWwVvUuTtSsRrQqPp",
                    "name": "Platform",
                    "roles": ["Admin"],
                    "users": ["alice@example.com"],
                }
            ],
            [
                {
                    "role_id": "AaBbCcDdEeFfGgHhIiJjKk",
                    "name": "Admin",
                    "teams": ["Platform"],
                    "users": ["alice@example.com"],
                }
            ],
        ],
        calls,
    )

    result = _run(["report", "team-roles", "--json", "--sanitize-uids"])

    assert result.exit_code == 0, result.output
    assert (
        secret_leak_check(
            result.stdout,
            env_keys=("KEEPER_PASSWORD", "KEEPER_TOTP_SECRET"),
        )
        == []
    )
    payload = json.loads(result.stdout)
    assert payload["command"] == "team-roles"
    assert payload["meta"]["team_count"] == 1
    assert payload["meta"]["role_count"] == 1
    assert [row["object_type"] for row in payload["rows"]] == ["team", "role"]
    assert calls[0][0:3] == ["enterprise-info", "-t", "-v"]
    assert calls[1][0:3] == ["enterprise-info", "-r", "-v"]
