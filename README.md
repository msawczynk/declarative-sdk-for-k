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
| `keeper-ksm.v1` | KSM applications | supported | App create wired (Commander + ownership marker); tokens/shares/app-updates are upstream-gap (exit 5 with next_action) |
| `keeper-enterprise.v1` | Teams, roles, nodes, enterprise-info | supported | Online validate/plan/diff supported; apply is read-only for enterprise roles/teams |
| `msp-environment.v1` | MSP managed companies | preview-gated | Discover/validate/plan supported; apply blocked — tenant MSP product permit required |

## Install

Requires Python 3.11+ (tested on 3.11, 3.12, 3.13) and `keepercommander>=17.2.16,<18` for the
See [COMPATIBILITY.md](docs/COMPATIBILITY.md) for the full version matrix.
`commander` provider. The mock provider runs offline.

```bash
pip install git+https://github.com/msawczynk/declarative-sdk-for-k.git@v2.1.0
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

## Known Limitations

The following capabilities are **not yet available** in this release:

| Limitation | Detail | Workaround |
|---|---|---|
| MSP managed-company apply | `CommanderCliProvider.apply_msp_plan` exits 5 — tenant requires MSP product permit (`msp_permits.allowed_mc_products`). Not a DSK or Commander bug. | Use `dsk plan` to verify intent; apply via Keeper admin console. |
| `pam rotation info --format=json` | Not implemented in Commander (upstream backlog). DSK can model `rotation_settings` in manifests; live rotation scheduling is blocked upstream. | Use `keeper pam rotation info` (human-readable output only). |
| Gateway create (`mode: create`) | Not implemented. DSK has no Commander surface to create a gateway. | Import existing gateways with `dsk import`; create new gateways via Keeper admin console. |
| KSM mutations beyond app create | `keeper-ksm.v1` supports app creation only. Token provisioning, record shares, app updates, and app deletion exit 5 with `next_action` on stderr. | Perform KSM token/share operations via Keeper Commander or Secrets Manager console. |
| JIT access, project creation | Upstream-gap — no Commander API available. Roadmap item for v2.x. | Use Keeper admin console. |
| Enterprise apply (roles/teams write) | `keeper-enterprise.v1` online validate/plan/diff are supported; apply for role and team mutations is read-only (Commander ACL limitation). | Apply enterprise changes via Keeper admin console. |

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
current full test gate is 1375 passed.

## License

MIT. See [`LICENSE`](LICENSE).
