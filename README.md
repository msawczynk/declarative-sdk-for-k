# declarative-sdk-for-k

> `dsk` — a declarative, agent-first SDK for Keeper tenant state:
> GA PAM lifecycle for machines, databases, directories, nested users,
> and remote browsers, plus scoped shared-folder, KSM, and typed-record
> surfaces. Rotation settings, JIT, gateway create, and RBI tuning remain
> preview-gated until live proof is complete.

Pure-Python core, no network I/O until you reach a provider. Machine-
readable everywhere (`--json`, typed exit codes, `next_action` on
every error). Designed so an LLM agent can plan, apply, and recover
from failure without a human in the loop.

**If you are an agent or LLM**: start at [`AGENTS.md`](AGENTS.md) for the
command table, exit-code contract, and JSON shapes. Scoped completion
contracts live in [`docs/SDK_DA_COMPLETION_PLAN.md`](docs/SDK_DA_COMPLETION_PLAN.md)
and [`docs/SDK_COMPLETION_PLAN.md`](docs/SDK_COMPLETION_PLAN.md). Cursor /
Codex / daybook orchestration is operator-side infrastructure and lives
in the maintainer's private daybook, not this repo.

## Capability scope

| Area                 | v1.0 coverage                        | Roadmap                      |
|----------------------|--------------------------------------|------------------------------|
| PAM resources        | machines, databases, directories, nested users, remote-browsers (GA lifecycle; preview-gated tuning gaps called out below) | rotation settings, standalone users, JIT, gateway `mode: create` (behind `DSK_PREVIEW=1`) |
| Gateways             | `reference_existing` mode            | `create` mode                |
| Shared folders       | scope + membership refs              | permissions matrix           |
| KSM applications     | reference_existing + share-bindings; **`dsk bootstrap-ksm` provisions an app + admin-record share + one-time client token + redeemed `ksm-config.json`**; `KsmLoginHelper` pulls Commander credentials *from* KSM (close the loop). Phase B inter-agent bus directory is provisioned but the client is sealed (`secrets/bus.py` raises `NotImplementedError`). | client-token rotation; bus client implementation |
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
  auth/                              # LoginHelper protocol + EnvLoginHelper / KsmLoginHelper reference impls
  secrets/                           # KSM as first-class SDK feature: bootstrap.py (Commander-driven
                                     # provisioning), ksm.py (KsmSecretStore + load_keeper_login_from_ksm),
                                     # bus.py (Phase B inter-agent bus directory — sealed skeleton)
  cli/                               # `dsk` (validate / export / plan / diff / apply / import / bootstrap-ksm)
tests/                               # 315 passing tests + 2 expected v1.1 deferrals (run pytest); coverage 86% (CI floor 84)
docs/
  COMMANDER.md                       # pinned Commander version + capability matrix
  LOGIN.md                           # login helper contract + 30-line skeleton
  KSM_BOOTSTRAP.md                   # `dsk bootstrap-ksm` operator runbook
  KSM_INTEGRATION.md                 # end-to-end bootstrap → KsmLoginHelper → SDK story
  VALIDATION_STAGES.md               # validate/plan/apply exit-code contract
AGENTS.md                            # agent-first operating manual
```

## Install

```bash
pip install -e '.[dev]'
# pinned version from GitHub (no PyPI package for this repo):
pip install git+https://github.com/msawczynk/declarative-sdk-for-k.git@v1.0.0
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
HSM-backed TOTP, device-approval queues, …),
[`docs/KSM_BOOTSTRAP.md`](docs/KSM_BOOTSTRAP.md) for the
Commander-driven KSM-app provisioning flow exposed as `dsk bootstrap-ksm`,
and [`docs/KSM_INTEGRATION.md`](docs/KSM_INTEGRATION.md) for the
end-to-end story (bootstrap → `ksm-config.json` → `KsmLoginHelper` →
fully credential-free SDK runs).
The built-in `EnvLoginHelper` is live-proven for a full `pamMachine`
validate -> plan -> apply -> verify -> destroy cycle. `KsmLoginHelper` is
green offline (264 unit tests in the KSM stack) and is the recommended
production helper once `dsk bootstrap-ksm` has produced a config.
Preview-gated surfaces such as RBI tuning and nested `pamUser` rotation
still need their own live proof before they become support claims.

### Quick start (KSM bootstrap)

```bash
# 1. Provision a KSM app + admin-record share + client token + ksm-config.json
#    (uses your already-logged-in Commander session by default; `--login-helper ksm`
#    or a custom path lets you bootstrap one KSM app from another).
dsk bootstrap-ksm --app-name my-sdk-app

# 2. Use the resulting config for credential-free SDK runs:
export KEEPER_SDK_KSM_CONFIG=~/.keeper/my-sdk-app-ksm-config.json
dsk --provider commander --login-helper ksm validate examples/pamMachine.yaml --online
```

The legacy `pamform` and `keeper-sdk` CLI names remain installed as
aliases for one major version so existing pipelines do not break.

## Status (main, 2026-04-26)

Core + mock: complete. Commander provider: discover, plan, apply
(create / update / delete via `keeper rm`, gated behind
`--allow-delete`), ownership-marker read/write, provider-level
capability check. Capability gaps (rotation, JIT, gateway `mode: create`)
surface as plan-time CONFLICT rows rather than silent drops, so the CLI's
`plan` and `apply --dry-run` agree before any mutation runs.
KSM is now a first-class SDK feature: `dsk bootstrap-ksm` provisions an
app + share + client token + `ksm-config.json` end-to-end, and
`KsmLoginHelper` reads Commander credentials back out of that vault — so
the SDK can authenticate without any plaintext env vars on the host.
Current local suite: **315 passing tests** + 2 expected v1.1 deferrals;
total line coverage **86.32%** (CI ratchet floor `84`); core modules
`redact`, `schema`, `normalize` at 100%.
Live `EnvLoginHelper` smoke proved full apply for `pamMachine`; Issue #5
RBI readback and Issue #4 nested-user rotation remain preview-gated until
their live create -> verify -> clean re-plan -> destroy loops pass.
`KsmLoginHelper` + `dsk bootstrap-ksm` are green offline; the live
end-to-end bootstrap → login → apply loop is the next gate.

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

