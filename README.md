# declarative-sdk-for-k

> `dsk` — a declarative, agent-first SDK covering the full K surface:
> vault records, shared folders, teams, roles, enterprise config, KSM
> apps, PAM (machines / databases / directories / users / remote
> browsers), compliance, rotation, migration.

Pure-Python core, no network I/O until you reach a provider. Machine-
readable everywhere (`--json`, typed exit codes, `next_action` on
every error). Designed so an LLM agent can plan, apply, and recover
from failure without a human in the loop.

**If you are an agent or LLM**: start at [`AGENTS.md`](AGENTS.md) for
the command table, exit-code contract, and JSON shapes. This README is
optimised for humans.

## Capability scope

| Area                 | v1.0 coverage                        | Roadmap                      |
|----------------------|--------------------------------------|------------------------------|
| PAM resources        | machines, databases, directories, users, remote-browsers (full declarative lifecycle) | rotation settings, JIT, gateway `mode: create` (behind `DSK_PREVIEW=1`) |
| Gateways             | `reference_existing` mode            | `create` mode                |
| Shared folders       | scope + membership refs              | permissions matrix           |
| KSM applications     | reference_existing + share-bindings  | app create + client rotation |
| Ownership markers    | read + write + adopt                 | multi-manager arbitration    |
| Vault records (non-PAM) | typed-model read/write via `login` resource | generic records, file records |
| Teams / roles        | discover surface only                | full declarative lifecycle   |
| Enterprise config    | not yet                              | SSO, SCIM, node tree         |
| Compliance / audit   | not yet                              | reports-as-manifest          |

The schema stays stable across capability additions — new top-level
blocks join `pam-environment.v1` rather than bumping the version. See
[`V1_GA_CHECKLIST.md`](V1_GA_CHECKLIST.md) for the commitment list
gating the `1.0.0` tag.

## Layout

```
keeper_sdk/                          # import path stable through 1.x
                                     # (renamed to declarative_sdk_k in 2.0 with a shim)
  core/                              # pure models, schema, graph, diff, planner, metadata, redact
    schemas/                         # packaged pam-environment.v1.schema.json
  providers/                         # MockProvider, CommanderCliProvider
  auth/                              # LoginHelper protocol + EnvLoginHelper reference impl
  cli/                               # `dsk` (validate / export / plan / diff / apply / import)
tests/                               # 182 passing tests + 2 expected v1.1 deferrals
docs/
  COMMANDER.md                       # pinned Commander version + capability matrix
  LOGIN.md                           # login helper contract + 30-line skeleton
  VALIDATION_STAGES.md               # validate/plan/apply exit-code contract
AGENTS.md                            # agent-first operating manual
```

## Install

```bash
pip install -e '.[dev]'
# once published to PyPI:
pip install declarative-sdk-for-k
```

Requires Python 3.11+. `keepercommander>=17.2.13,<18` is pulled in
automatically — only exercised when you hit the `commander` provider;
the mock provider works standalone.

## Quick start (offline, mock provider)

```bash
dsk validate examples/pamMachine.yaml
dsk --provider mock plan examples/pamMachine.yaml --json
dsk --provider mock apply examples/pamMachine.yaml --auto-approve
```

## Quick start (live tenant)

```bash
export KEEPER_EMAIL='you@example.com'
export KEEPER_PASSWORD='...'
export KEEPER_TOTP_SECRET='JBSWY3DPEHPK3PXP'      # base32 secret, NOT a 6-digit code
export KEEPER_DECLARATIVE_FOLDER='<shared-folder-uid>'

dsk --provider commander validate examples/pamMachine.yaml --online
dsk --provider commander plan     examples/pamMachine.yaml
```

See [`docs/LOGIN.md`](docs/LOGIN.md) for custom login flows (KSM pull,
HSM-backed TOTP, device-approval queues, …).
The built-in `EnvLoginHelper` live proof currently covers validate, plan,
and sandbox provisioning; full live apply has a deferred Commander
session-refresh gap tracked for v1.1. Use a custom helper for apply only
after validating that refresh path in your tenant.

The legacy `pamform` and `keeper-sdk` CLI names remain installed as
aliases for one major version so existing pipelines do not break.

## Status (main, 2026-04-25)

Core + mock: complete. Commander provider: discover, plan, apply
(create / update / delete via `keeper rm`, gated behind
`--allow-delete`), ownership-marker read/write, provider-level
capability check. Capability gaps (rotation, JIT, gateway `mode: create`)
surface as plan-time CONFLICT rows rather than silent drops, so
`plan == apply --dry-run == apply` for every manifest + provider pair.
Current local suite: 182 passing tests + 2 expected v1.1 deferrals.
Live `EnvLoginHelper` smoke proved the login contract (validate, plan,
and sandbox provisioning); full apply is deferred behind a Commander
session-refresh gap tracked for v1.1.

## Exit codes

| code | command    | meaning                    |
|------|------------|----------------------------|
| 0    | plan/diff  | clean plan                 |
| 0    | apply      | applied successfully       |
| 0    | validate   | manifest ok                |
| 1    | any        | unexpected error           |
| 2    | plan/diff  | changes present            |
| 2    | validate   | schema failure             |
| 3    | any        | uid_ref / graph / cycle    |
| 4    | plan/diff  | conflicts present          |
| 4    | apply      | conflicts refused apply    |
| 5    | any        | capability / provider fail |

## Programmatic use

```python
from keeper_sdk.core import (
    load_manifest, build_graph, execution_order,
    compute_diff, build_plan,
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

`compute_diff` has a keyword-only `adopt=False` flag. Unmanaged live records
that match a manifest resource by title surface as `CONFLICT` by default; pass
`adopt=True` (or the future `keeper-sdk import` subcommand, per W18) to write
ownership markers over them.

## Testing

```bash
pytest
```

Tests cover manifest load/dump, canonicalisation, Commander payload
normalisation, schema + semantic validation, preview gates, graph order,
diff taxonomy, provider contracts, CLI JSON/exit-code surfaces, stage-5
tenant binding checks, renderer snapshots, DOR scenario regressions, and
a 500-resource performance/memory smoke.

CLI smokes exercise `validate`, `export`, `plan` exit codes (`0`/`2`/`4`),
`apply --dry-run` equivalence to `plan`, and JSON output. Live-smoke
variants live under `scripts/smoke/` and can be selected with
`--scenario` plus `--login-helper deploy_watcher|env`.


