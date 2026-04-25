# AGENTS.md — operating manual for LLM / agent consumers

This repository is designed for autonomous agents. If you are an LLM
reading this file, treat it as the authoritative quick-reference. It is
deliberately machine-parseable: tables with stable columns, code blocks
with shell-runnable commands, exit codes as integers, JSON examples.

## What this is

`dsk` (declarative-sdk-for-k) turns a YAML / JSON manifest describing
K-tenant state — PAM resources today (gateways, `pam_configuration`s,
machines, databases, directories, users, remote-browsers), expanding to
vault records, shared folders, teams, roles, enterprise config, KSM
apps, compliance, and rotation — into a declarative lifecycle:

```text
validate -> plan -> apply
           |
           +-> diff (field-level)
           +-> import (adopt unmanaged records)
           +-> export (lift existing Commander JSON into a manifest)
```

Everything is deterministic, dry-runnable, and speaks exit codes.

## One-line mental model for agents

> A manifest is the **source of truth**. A `plan` is the **delta**
> between the manifest and the live tenant. `apply` executes the plan
> and writes ownership markers. The SDK **never** touches records it
> does not own.

## Install

```bash
pip install -e ".[dev]"              # contributor install (this repo)
pip install git+https://github.com/msawczynk/declarative-sdk-for-k.git@main
# or a release tag / wheel from GitHub Releases — see docs/RELEASING.md
```

Python 3.11+. Requires `keepercommander>=17.2.13,<18` installed and a
reachable Keeper tenant for the `commander` provider. The `mock`
provider runs fully offline and is the recommended starting point for
agents.

## Command table (all machine-readable)

| Command             | Input                | Output                 | Machine flag          |
|---------------------|----------------------|------------------------|-----------------------|
| `dsk validate PATH` | manifest YAML/JSON   | `ok: <name> (<n>refs)` | `--emit-canonical`    |
| `dsk plan PATH`     | manifest             | plan summary + table   | `--json`              |
| `dsk diff PATH`     | manifest             | field-level diff       | —                     |
| `dsk apply PATH`    | manifest             | outcomes table         | `--dry-run`           |
| `dsk import PATH`   | manifest             | adoption plan          | `--dry-run`           |
| `dsk export JSON`   | `pam project export` | manifest YAML          | `-o FILE`             |

Aliases `pamform` and `keeper-sdk` resolve to the same entrypoint for
backward compatibility with pre-1.0 callers; they will be removed in 2.0.

Every mutating command honours `--auto-approve` (skip prompts) and
`--allow-delete` (permit delete rows in the plan).

## Exit codes — binding contract

| Code | Meaning                             | Action for agent                               |
|------|-------------------------------------|------------------------------------------------|
| 0    | success / clean plan                | continue                                       |
| 1    | unexpected error                    | inspect stderr; likely retry once, then report |
| 2    | schema invalid (validate) OR changes present (plan/diff) | distinguish by subcommand — `validate`=failure, `plan`/`diff`=informational |
| 3    | unresolved uid_ref / cycle          | operator must fix manifest links               |
| 4    | plan has conflicts                  | `plan --json` → iterate `changes[*].reason`    |
| 5    | provider / capability error         | `stderr` carries `next_action`; apply it       |

Exit 2 is overloaded intentionally — see `docs/VALIDATION_STAGES.md`.
Disambiguate via the subcommand you invoked. CI pipelines depend on
this. Do not propose changes to the numbering without a spec update.

For the per-stage breakdown of what `validate` checks and which exit
code fires for which failure (schema vs reference vs capability vs
binding), read [`docs/VALIDATION_STAGES.md`](./docs/VALIDATION_STAGES.md).

## Autonomous execution (maintainer grant)

Maintainers grant **standing permission** to run this repo’s scripted gates and
live smoke (`scripts/agent/phase0_gates.sh`, `scripts/smoke/smoke.py`,
`scripts/agent/codex_live_smoke.sh` when scoped) without asking for approval
before each command—**when** the lab machine already has Commander + the
expected `keeper-vault-rbi-pam-testenv` configs (see `scripts/smoke/README.md`).
Agents still must not echo secrets, must use the smoke harness (not ad-hoc
tenant edits), and must treat failures as evidence (fix, document, or stop per
`docs/SDK_DA_COMPLETION_PLAN.md`).

## Agent playbook

### A. "Apply this manifest"

```bash
dsk validate env.yaml                        # gate 1: schema
dsk plan env.yaml --json > /tmp/plan.json    # gate 2: inspect machine-readable
# Parse /tmp/plan.json; if summary.conflict > 0 -> abort with the reasons
dsk apply env.yaml --auto-approve            # gate 3: execute
```

Abort conditions for the agent:

- Exit 3 from `validate` → manifest has a bad uid_ref. Report the
  `reference error:` stderr line verbatim; do not guess a fix.
- Exit 4 from `plan` → read `changes[*].reason` from JSON; capability
  gaps come as `resource_type: "capability"` rows and carry the exact
  Commander hook that would be needed to implement them.
- Any non-zero exit from `apply` after a clean plan → **do not retry
  blindly**. Re-run `plan` first; silent drift is the bigger risk
  than a transient failure.

### B. "Adopt what already exists"

```bash
dsk import env.yaml --dry-run                # see what would be claimed
dsk import env.yaml --auto-approve           # write ownership markers
```

Adoption only matches records with **no** existing marker. If a record
already belongs to another `manager` string, it shows as CONFLICT and
`import` refuses to touch it.

### C. "Recreate this environment somewhere else"

```bash
keeper pam project export --output project.json  # upstream Commander
dsk export project.json -o env.yaml          # lift to a manifest
dsk validate env.yaml
dsk apply env.yaml                           # on the new tenant
```

### D. "Debug a drift"

```bash
dsk diff env.yaml > diff.txt                 # human-readable
dsk plan env.yaml --json | jq '.changes[] | select(.kind=="update")'
```

## JSON contracts agents can parse

### `dsk plan --json` → shape

```json
{
  "manifest_name": "acme-lab-minimal",
  "summary": { "create": 0, "update": 0, "delete": 0, "conflict": 0, "noop": 5 },
  "order": ["gw.lab", "cfg.aws", "res.db-prod"],
  "changes": [
    {
      "kind": "update",
      "uid_ref": "res.db-prod",
      "resource_type": "pamDatabase",
      "title": "prod-mysql",
      "keeper_uid": "ABC123...",
      "before": { "host": "old.example.com", "password": "***redacted***" },
      "after":  { "host": "new.example.com", "password": "***redacted***" },
      "reason": null
    }
  ]
}
```

`before` / `after` are **redacted** at the renderer level — actual
secret values never leave the process (see `keeper_sdk.core.redact`).

### Capability conflicts (exit 4)

```json
{ "kind": "conflict",
  "resource_type": "capability",
  "title": "unsupported-by-provider",
  "reason": "resources[].rotation_settings is not implemented (Commander hook: `pam rotation edit --schedulejson / --schedulecron`)" }
```

The `reason` is the copy-paste fix — it names the exact Commander verb
an operator (or a future agent with rotation coverage) would need to
drive.

## Login for the `commander` provider

Set one of:

**Quickstart (this SDK's reference helper):**

```bash
export KEEPER_EMAIL='you@example.com'
export KEEPER_PASSWORD='...'
export KEEPER_TOTP_SECRET='JBSWY3DPEHPK3PXP'   # base32, NOT a 6-digit code
# optional:
export KEEPER_SERVER='keepersecurity.com'
export KEEPER_CONFIG='/path/to/keeper-config.json'
```

**Custom helper (KSM pull, device approval, etc.):**

```bash
export KEEPER_SDK_LOGIN_HELPER=/abs/path/to/your_helper.py
```

See `docs/LOGIN.md` for the 30-line helper skeleton.

## Guardrails — things agents MUST NOT do

1. **Never delete ownership markers manually.** The SDK treats
   unmarked records as unmanaged; stripping the marker field causes
   the next `plan` to either ignore the record or adopt it — both
   confusing.
2. **Never edit the manifest AND the live tenant in the same turn.**
   Change one, plan to see the drift, then converge. Editing both is
   how agents turn a 2-line drift into a 200-line diff.
3. **Never retry `apply` on exit 5 without reading `next_action`.**
   Exit 5 is a provider capability signal — rotation not implemented,
   login failed, gateway missing. The `next_action` string on
   `stderr` is the fix; retrying without addressing it loops forever.
4. **Never commit a manifest that has `rotation_settings`,
   `jit_settings`, or `gateway.mode: create` until this SDK implements
   them.** Validation passes; `apply` converts them to CONFLICT rows;
   the tenant state is unchanged but the manifest contains a lie.

## Orchestration — use Codex CLI first

Canonical split + Phase 0 + parallel tracks: **[`docs/ORCHESTRATION_PHASE0_PARALLEL.md`](./docs/ORCHESTRATION_PHASE0_PARALLEL.md)**. Non-agentic gates: **`scripts/agent/phase0_gates.sh quick`** (iterate) and **`full`** (pre-merge).

For **scoped implementation** (new tests, provider wiring, docs), the default workflow is **parent delegates to Codex CLI**, not a single long Cursor turn:

1. Parent writes a prompt file: task, **hard file scope**, success criteria, **allowed commands** (e.g. `python3 -m pytest -q tests/test_foo.py`, `ruff check path`), and the DONE footer from `.github/codex/prompts/scoped-task.md`.
2. Parent runs `scripts/agent/codex_offline_slice.sh` against that file (see [`docs/CODEX_CLI.md`](./docs/CODEX_CLI.md)).
3. Parent reviews the patch, runs **`phase0_gates.sh`** (or full CI parity), owns **live smoke** and **gate lifts**, **pushes to GitHub**.

GitHub Codex (issues, Actions) is optional for async work — [`docs/CODEX_GITHUB.md`](./docs/CODEX_GITHUB.md).

**Token / style (every agent, including workers):** user-visible text → **caveman-ultra** (short, fragments, abbrev, `→`). Hidden reasoning → **wenyan-ultra** only where the product separates thinking from chat — never paste 文言 to humans. Workers: prepend maintainer `AGENT_PREAMBLE.md` when available; see [`.cursorrules`](./.cursorrules) and [`docs/CODEX_CLI.md`](./docs/CODEX_CLI.md) § token efficiency.

## Where to read next

- `README.md` — human-oriented overview.
- `docs/COMMANDER.md` — pinned Commander version + capability matrix.
- `docs/SDK_DA_COMPLETION_PLAN.md` — current devil's-advocate completion
  gates, phases, and stop conditions.
- `docs/SDK_ORCHESTRATED_FEATURE_COMPLETE.md` — master table: phases × gates ×
  Codex/live proofs (orchestration index).
- `docs/SDK_COMPLETION_PLAN.md` — parent/Codex orchestration roadmap.
- `docs/CODEX_CLI.md` — local `codex exec` as default worker; scripts under `scripts/agent/`.
- `docs/ORCHESTRATION_PHASE0_PARALLEL.md` — Phase 0 clean tree, parallel Codex slices, scripted gates.
- `docs/LOGIN.md` — custom-helper contract.
- `V1_GA_CHECKLIST.md` — roadmap toward v1.0.0 GA.
- `AUDIT.md` — milestone history + reconciliation with the upstream DOR.
- `REVIEW.md` — devil's-advocate review notes (what was deferred, why).
