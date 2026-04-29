# DSK MCP Server

`dsk-mcp` exposes DSK lifecycle operations as Model Context Protocol tools for
AI agents. It complements Keeper's KSM MCP servers: KSM MCP handles secret CRUD,
while DSK MCP handles declarative PAM infrastructure lifecycle.

## Architecture

| Layer | Role |
|---|---|
| KSM MCP | Secret records, app configs, and secret CRUD. |
| DSK MCP | `validate`, `plan`, `diff`, `apply`, `export`, reports, and KSM bus calls for declarative PAM state. |

The server speaks JSON-RPC 2.0 over stdio and calls DSK Python APIs in-process.
It does not shell out to `dsk`. If `KEEPER_SERVICE_URL` and
`KEEPER_SERVICE_API_KEY` are set, lifecycle tools try to use a
`CommanderServiceProvider` extension. Without those variables, the server uses
`MockProvider` for offline operation.

## Setup

Install the package in editable or normal form:

```bash
pip install -e ".[dev]"
dsk-mcp
```

Cursor / Claude Desktop style config:

```json
{
  "mcpServers": {
    "dsk": {
      "command": "dsk-mcp",
      "env": {
        "KEEPER_SERVICE_URL": "http://localhost:4020",
        "KEEPER_SERVICE_API_KEY": "${DSK_API_KEY}"
      }
    }
  }
}
```

For offline tests or local demos, omit both service env vars.

## Tools

| Tool | Inputs | Output |
|---|---|---|
| `dsk_validate` | `manifest_yaml` | `ok` or validation/capability/reference error text. |
| `dsk_plan` | `manifest_yaml`, `allow_delete=false` | Redacted JSON plan with `summary`, `order`, and `changes`. |
| `dsk_apply` | `manifest_yaml`, `auto_approve=true`, `dry_run=false` | Redacted outcomes JSON. Rejects `auto_approve=false`. |
| `dsk_diff` | `manifest_yaml` | Redacted field-level diff text. |
| `dsk_export` | `project_json` | Redacted DSK manifest YAML. |
| `dsk_report` | `report_type`, `sanitize_uids=true` | Redacted report envelope for password, compliance, or security-audit reports. |
| `dsk_bus_publish` | `channel`, `payload`, `record_uid` | KSM bus channel/version JSON. |
| `dsk_bus_get` | `channel`, `record_uid` | Latest KSM bus value/version JSON. |

## Security

- `dsk_apply` requires explicit `auto_approve=true`; `false` is rejected before
  planning or provider calls.
- Tool results pass through the SDK redactor, and plan/report renderers already
  redact secret-flavored fields.
- `dsk_export` redacts secret fields before returning YAML.
- Offline mode uses `MockProvider` and does not touch Commander or live Keeper
  network APIs.
- Live/service mode is opt-in through `KEEPER_SERVICE_URL` plus
  `KEEPER_SERVICE_API_KEY`; missing service-provider support fails closed with
  a `next_action`.
