from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from keeper_sdk.mcp import server as mcp_server

VALID_VAULT = """\
schema: keeper-vault.v1
records:
  - uid_ref: mcp.login
    type: login
    title: MCP Login
    fields:
      - type: login
        label: Login
        value: ["agent@example.invalid"]
      - type: password
        label: Password
        value: ["never-return-me"]
"""


INVALID_MANIFEST = """\
schema: keeper-vault.v1
records:
  - title: Missing uid_ref
"""


NHI_MANIFEST = """\
schema: nhi-agent.v1
resources: []
"""


AI_AGENT_MANIFEST = """\
schema: ai-agent.v1
resources: []
"""


def test_dsk_validate_valid_manifest_returns_ok() -> None:
    assert _run(mcp_server.validate(VALID_VAULT)) == "ok"


def test_dsk_validate_invalid_manifest_returns_error_string() -> None:
    output = _run(mcp_server.validate(INVALID_MANIFEST))
    assert "validation failed" in output or "reference error" in output


def test_dsk_plan_returns_json_with_summary() -> None:
    payload = json.loads(_run(mcp_server.plan(VALID_VAULT)))
    assert payload["summary"]["create"] == 1
    assert payload["summary"]["conflict"] == 0
    assert payload["changes"][0]["after"]["fields"][1]["value"] == ["***redacted***"]


def test_dsk_apply_with_auto_approve_false_raises() -> None:
    with pytest.raises(ValueError, match="auto_approve=True"):
        _run(mcp_server.apply(VALID_VAULT, auto_approve=False))


def test_dsk_apply_dry_run_returns_redacted_outcomes() -> None:
    payload = json.loads(_run(mcp_server.apply(VALID_VAULT, dry_run=True)))
    assert payload["dry_run"] is True
    assert payload["outcomes"][0]["action"] in {"create", "noop"}
    assert "never-return-me" not in json.dumps(payload)


def test_dsk_diff_redacts_secrets() -> None:
    output = _run(mcp_server.diff(VALID_VAULT))
    assert "never-return-me" not in output
    assert "***redacted***" in output


def test_dsk_report_redacts_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_report(args: list[str]) -> None:
        print(
            json.dumps(
                {
                    "command": args[0],
                    "rows": [{"record_uid": "UID123", "password": "plain-secret"}],
                }
            )
        )

    monkeypatch.setattr(mcp_server, "_invoke_report_cli", fake_report)
    output = _run(mcp_server.report("password-report"))
    assert "plain-secret" not in output
    assert "***redacted***" in output


def test_server_initializes_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KEEPER_SERVICE_URL", raising=False)
    monkeypatch.delenv("KEEPER_SERVICE_API_KEY", raising=False)
    tools = mcp_server.server.list_tools()
    assert {tool["name"] for tool in tools} >= {"dsk_validate", "dsk_plan", "dsk_apply"}
    validate_tool = next(tool for tool in tools if tool["name"] == "dsk_validate")
    assert "nhi-agent.v1" in validate_tool["description"]
    assert "ai-agent.v1" in validate_tool["description"]


def test_json_rpc_tools_list() -> None:
    response = _run(mcp_server.server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
    assert response["result"]["tools"]


def test_json_rpc_tools_call() -> None:
    response = _run(
        mcp_server.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "dsk_validate", "arguments": {"manifest_yaml": VALID_VAULT}},
            }
        )
    )
    assert response["result"]["content"][0]["text"] == "ok"
    assert response["result"]["isError"] is False


@pytest.mark.parametrize(
    ("family", "manifest_yaml"),
    [("nhi-agent.v1", NHI_MANIFEST), ("ai-agent.v1", AI_AGENT_MANIFEST)],
)
def test_mcp_plan_registers_nhi_ai_agent_families_as_upstream_gap(
    family: str,
    manifest_yaml: str,
) -> None:
    pytest.importorskip("keeper_sdk.core.models_nhi")  # skip in public build (private family)
    response = _run(
        mcp_server.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "dsk_plan", "arguments": {"manifest_yaml": manifest_yaml}},
            }
        )
    )
    text = response["result"]["content"][0]["text"]
    assert response["result"]["isError"] is True
    assert family in text
    assert "upstream-gap" in text
    assert "NHI PAM API GA" in text


def test_bus_publish_and_get(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeBus:
        value = None
        version = 0

        def __init__(self, store: object, record_uid: str) -> None:
            assert record_uid == "REC"

        def publish(self, channel: str, payload: dict[str, object]) -> int:
            assert channel == "chan"
            type(self).version += 1
            type(self).value = payload
            return type(self).version

        def get(self, channel: str) -> object:
            assert channel == "chan"
            if type(self).value is None:
                return None
            return SimpleNamespace(value=type(self).value, version=type(self).version)

    monkeypatch.setattr(mcp_server, "KsmSecretStore", lambda: object())
    monkeypatch.setattr(mcp_server, "KsmBus", FakeBus)
    published = json.loads(_run(mcp_server.bus_publish("chan", {"password": "secret"}, "REC")))
    fetched = json.loads(_run(mcp_server.bus_get("chan", "REC")))
    assert published["version"] == 1
    assert fetched["value"]["password"] == "***redacted***"


def _run(awaitable):
    return asyncio.run(awaitable)
