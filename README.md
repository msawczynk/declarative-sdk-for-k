# declarative-sdk-for-k

Declarative lifecycle management for Keeper Security tenants.

## What It Does

- Validates YAML or JSON manifests for supported Keeper tenant state.
- Plans deterministic deltas between the manifest and the tenant or mock provider.
- Applies ownership-safe changes, with dry-run behavior and typed exit codes for automation.

## Supported Manifest Families

| Manifest family | Scope | Status | Notes |
|---|---|---|---|
| `pam-environment.v1` | PAM gateways, configurations, machines, databases, directories, users, and remote browsers | supported | Full lifecycle for supported PAM resources |
| `keeper-vault.v1` | Vault records, including the `login` type | supported | Login L1 lifecycle |
| `keeper-vault-sharing.v1` | Shared folders and record shares | supported | Shared-folder and record-share lifecycle |
| `keeper-ksm.v1` | KSM applications, tokens, and shares | supported | App create plus offline token/share coverage |
| `keeper-enterprise.v1` | Teams, roles, and nodes | upstream-gap | Read/validate surfaces are available |
| `msp-environment.v1` | MSP managed companies | upstream-gap | Read/validate/plan are available; apply is pending |

## Install

Requires Python 3.11+ and `keepercommander>=17.2.16,<18` for the
`commander` provider. The mock provider runs offline.

```bash
pip install git+https://github.com/msawczynk/declarative-sdk-for-k.git
pip install -e ".[dev]"
```

Development uses a two-repo model: active development happens in
`github.com/msawczynk/dsk`; the public mirror is
`github.com/msawczynk/declarative-sdk-for-k`.

## Quick Start

```bash
dsk validate examples/pamMachine.yaml
dsk --provider mock plan examples/pamMachine.yaml --json
dsk --provider mock apply examples/pamMachine.yaml --dry-run
dsk --provider mock apply examples/pamMachine.yaml --auto-approve
dsk --provider mock plan examples/pamMachine.yaml
```

## CLI Commands

| Command | Input | Output | Machine flag |
|---|---|---|---|
| `dsk validate PATH` | manifest YAML/JSON | validation result; PAM and vault also run typed graph checks | `--emit-canonical`, `--json`, `--online` |
| `dsk plan PATH` | manifest | plan summary and change table | `--json` |
| `dsk diff PATH` | manifest | field-level diff | - |
| `dsk apply PATH` | manifest | outcomes table | `--dry-run` |
| `dsk import PATH` | manifest | adoption plan | `--dry-run` |
| `dsk export JSON` | Commander-shaped PAM project JSON | manifest YAML | `-o FILE` |
| `dsk report password-report` | Commander session | redacted JSON envelope | `--sanitize-uids`, `--quiet` |
| `dsk report compliance-report` | Commander session | redacted JSON envelope | `--sanitize-uids`, `--quiet`, `--node`, `--rebuild` |
| `dsk report security-audit-report` | Commander session | redacted JSON envelope | `--record-details`, `--sanitize-uids`, `--quiet`, `--node` |
| `dsk report ksm-usage` | KSM or Commander state | redacted usage envelope | `--json`, `--sanitize-uids` |

Mutating commands honor `--auto-approve`. Deletes require `--allow-delete`.

## Exit Codes

| Code | Meaning | Action for automation |
|---:|---|---|
| `0` | success or clean plan | continue |
| `1` | unexpected error | inspect stderr; retry only when the failure is transient |
| `2` | schema invalid for `validate`, changes present for `plan`/`diff` | branch by subcommand |
| `3` | unresolved `uid_ref` or dependency cycle | fix manifest links |
| `4` | plan has conflicts | inspect `plan --json` and read `changes[*].reason` |
| `5` | provider or capability error | follow the `next_action` printed on stderr |

## Programmatic Use

PAM manifests use the PAM loader and graph helpers:

```python
from keeper_sdk.core import (
    build_graph,
    build_plan,
    compute_diff,
    execution_order,
    load_manifest,
)
from keeper_sdk.providers import MockProvider

manifest = load_manifest("env.yaml")
provider = MockProvider(manifest.name)

graph = build_graph(manifest)
order = execution_order(graph)
changes = compute_diff(manifest, provider.discover())
plan = build_plan(manifest.name, changes, order)
provider.apply_plan(plan)
```

Vault manifests use the declarative loader and vault-specific graph/diff helpers:

```python
from keeper_sdk.core.manifest import load_declarative_manifest
from keeper_sdk.core.planner import build_plan
from keeper_sdk.core.vault_diff import compute_vault_diff
from keeper_sdk.core.vault_graph import build_vault_graph, vault_record_apply_order
from keeper_sdk.providers import MockProvider

manifest = load_declarative_manifest("vault.yaml")
provider = MockProvider("vault-example")

graph = build_vault_graph(manifest)
order = vault_record_apply_order(graph)
changes = compute_vault_diff(manifest, provider.discover())
plan = build_plan("vault-example", changes, order)
provider.apply_plan(plan)
```

## MCP Server

`dsk-mcp` exposes validate, plan, apply, diff, export, report, and KSM bus tools
over stdio JSON-RPC for MCP clients. Use the same provider credentials and
approval posture you would use for the CLI.

## KSM Inter-Agent Bus

The KSM inter-agent bus provides a CAS-style coordination protocol for
`acquire`, `release`, `publish`, and `consume`, plus `MockBusStore` for offline
tests. It is intended for coordination metadata and agent messages, not for
printing or logging secrets.

## Reporting

`dsk report` includes:

- `password-report`
- `compliance-report`
- `security-audit-report`
- `ksm-usage`

Report output is wrapped in a redacted envelope. UID fingerprinting is available
with `--sanitize-uids` where supported.

## Provider Login

For the `commander` provider, set `KEEPER_EMAIL`, `KEEPER_PASSWORD`, and
`KEEPER_TOTP_SECRET`, or provide a custom helper with
`KEEPER_SDK_LOGIN_HELPER=/path/to/helper.py`. See
[`docs/LOGIN.md`](docs/LOGIN.md) for the helper contract and examples.

## Contributing And Development

Public issues and pull requests are welcome on
`github.com/msawczynk/declarative-sdk-for-k`. Maintainers may mirror accepted
changes through the private development repository before publication. The
current full test gate is 1453 passed.

## License

MIT. See [`LICENSE`](LICENSE).
