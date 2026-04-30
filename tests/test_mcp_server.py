"""Offline tests for keeper_sdk.mcp.server.

No live Keeper calls. Uses mock provider where a manifest is needed.
"""
from __future__ import annotations

import asyncio
import textwrap

import pytest

# ── importability ─────────────────────────────────────────────────────────────


def test_import_json_rpc_mcp_server() -> None:
    """JsonRpcMcpServer must be importable without network."""
    from keeper_sdk.mcp.server import JsonRpcMcpServer  # noqa: PLC0415

    assert callable(JsonRpcMcpServer)


def test_import_main() -> None:
    """main() must be importable (not called — that would block on stdio)."""
    from keeper_sdk.mcp.server import main  # noqa: PLC0415

    assert callable(main)


# ── valid manifest fixtures ────────────────────────────────────────────────────

# Minimal pam-environment.v1: version + schema + name only (no extra fields).
_PAM_YAML = textwrap.dedent("""\
    version: "1"
    name: test-pam
    schema: pam-environment.v1
""")

# Minimal keeper-vault.v1: schema + empty records list.
_VAULT_YAML = textwrap.dedent("""\
    schema: keeper-vault.v1
    records: []
""")


# ── tool: validate ─────────────────────────────────────────────────────────────


def test_validate_tool_pam() -> None:
    """validate() tool returns 'ok' for a valid PAM manifest."""
    from keeper_sdk.mcp.server import validate  # noqa: PLC0415

    result = asyncio.run(validate(_PAM_YAML))
    assert result == "ok", f"Expected 'ok', got: {result!r}"


def test_validate_tool_vault() -> None:
    """validate() tool returns 'ok' for a minimal vault manifest."""
    from keeper_sdk.mcp.server import validate  # noqa: PLC0415

    result = asyncio.run(validate(_VAULT_YAML))
    assert result == "ok", f"Expected 'ok', got: {result!r}"


def test_validate_tool_missing_version() -> None:
    """validate() returns non-ok error string for schema violation."""
    from keeper_sdk.mcp.server import validate  # noqa: PLC0415

    # missing 'version' → schema validation failure
    bad = "name: no-version\nschema: pam-environment.v1\n"
    result = asyncio.run(validate(bad))
    assert result != "ok"
    assert "version" in result.lower() or "validation" in result.lower()


def test_validate_tool_invalid_schema_family() -> None:
    """validate() returns error for unknown schema family."""
    from keeper_sdk.mcp.server import validate  # noqa: PLC0415

    yaml = 'version: "1"\nname: bad\nschema: nonexistent-family.v99\n'
    result = asyncio.run(validate(yaml))
    assert result != "ok"


# ── tool: bad YAML propagates as exception (server wraps in isError) ──────────


def test_validate_bad_yaml_via_server_call_tool() -> None:
    """call_tool() wraps YAML parse errors in isError content instead of raising."""
    from keeper_sdk.mcp.server import server  # noqa: PLC0415

    bad = "this: is: not: valid: yaml: :\n  - broken"
    result = asyncio.run(server.call_tool("dsk_validate", {"manifest_yaml": bad}))
    # call_tool catches exceptions → returns isError=True content block
    assert result["isError"] is True
    assert len(result["content"]) > 0
    assert result["content"][0]["type"] == "text"


# ── JSON-RPC request/response shape (via server.handle) ───────────────────────


def test_json_rpc_validate_response_shape() -> None:
    """server.handle() for dsk_validate returns valid JSON-RPC 2.0 envelope."""
    from keeper_sdk.mcp.server import server  # noqa: PLC0415

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "dsk_validate",
            "arguments": {"manifest_yaml": _PAM_YAML},
        },
    }
    response = asyncio.run(server.handle(request))

    assert isinstance(response, dict), f"Expected dict, got {type(response)}"
    assert response.get("id") == 1
    assert "result" in response or "error" in response

    if "result" in response:
        content = response["result"].get("content", [])
        assert isinstance(content, list)
        assert len(content) > 0
        text_block = content[0]
        assert text_block.get("type") == "text"
        assert "ok" in text_block.get("text", "")


def test_json_rpc_tools_list() -> None:
    """tools/list returns list of tool descriptors including dsk_validate."""
    from keeper_sdk.mcp.server import server  # noqa: PLC0415

    request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    response = asyncio.run(server.handle(request))

    assert response is not None
    assert response.get("id") == 2
    assert "result" in response
    tools = response["result"]["tools"]
    names = [t["name"] for t in tools]
    assert "dsk_validate" in names


def test_json_rpc_unknown_method() -> None:
    """server.handle() returns JSON-RPC error for unknown method."""
    from keeper_sdk.mcp.server import server  # noqa: PLC0415

    request = {
        "jsonrpc": "2.0",
        "id": 42,
        "method": "tools/call",
        "params": {
            "name": "dsk_nonexistent_tool",
            "arguments": {},
        },
    }
    response = asyncio.run(server.handle(request))
    assert isinstance(response, dict)
    assert response.get("id") == 42
    assert "error" in response


# ── CLI: dsk mcp --help ────────────────────────────────────────────────────────


def test_dsk_mcp_help() -> None:
    """dsk mcp --help must exit 0 and show 'serve'."""
    from click.testing import CliRunner

    from keeper_sdk.cli.main import main  # noqa: PLC0415

    runner = CliRunner()
    result = runner.invoke(main, ["mcp", "--help"])
    assert result.exit_code == 0, result.output
    assert "serve" in result.output


def test_dsk_mcp_serve_help() -> None:
    """dsk mcp serve --help must exit 0 and describe the stdio server."""
    from click.testing import CliRunner

    from keeper_sdk.cli.main import main  # noqa: PLC0415

    runner = CliRunner()
    result = runner.invoke(main, ["mcp", "serve", "--help"])
    assert result.exit_code == 0, result.output
    assert "stdio" in result.output.lower() or "mcp" in result.output.lower()
