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
| `dsk validate PATH` | manifest YAML/JSON   | PAM: `ok: <name> (<n>refs)`; `keeper-vault.v1`: typed graph offline, optional `--online` (Commander); other packaged families: schema stages only unless extended | `--emit-canonical`, `--json`, `--online` |
| `dsk plan PATH`     | manifest             | plan summary + table (`pam-environment.v1` + `keeper-vault.v1`; vault `login` diff matches manifest `fields[]` to Commander-flattened scalars) | `--json`              |
| `dsk diff PATH`     | manifest             | field-level diff (same vault `login` semantics as `plan`) | —                     |
| `dsk apply PATH`    | manifest             | outcomes table         | `--dry-run`           |
| `dsk import PATH`   | manifest             | adoption plan          | `--dry-run`           |
| `dsk export JSON`   | `pam project export` | manifest YAML          | `-o FILE`             |
| `dsk report password-report` | Commander session | redacted JSON envelope | `--sanitize-uids` (fingerprint UIDs in values); `--quiet` (also fingerprint `record_uid` / `shared_folder_uid` keys); leak check → exit **1** |
| `dsk report compliance-report` | Commander session | redacted JSON envelope | `--sanitize-uids`, `--quiet`, `--node`, `--rebuild`; leak check → exit **1** |
| `dsk report security-audit-report` | Commander session | redacted JSON envelope | `--record-details`, `--sanitize-uids`, `--quiet`, `--node`; leak check → exit **1** |

**msp-environment.v1 (commander):** `dsk validate --online` runs MSP discover (needs MSP admin session). Commander `import` / `apply` stay unsupported; see `docs/COMMANDER.md` (MSP section).

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

**`keeper-vault.v1`:** `plan` / `diff` / `validate --online` compare manifest
`login` ``fields[]`` to Commander-flattened scalars **best-effort** (duplicate
labels, non-scalar typed values, and Commander shape skew can still mislead).
`validate --online` is a **point-in-time** snapshot — another client can change
records before `apply`. Read the **Vault — operator caveats** section in
[`docs/VALIDATION_STAGES.md`](./docs/VALIDATION_STAGES.md) and
[`docs/VAULT_L1_DESIGN.md`](./docs/VAULT_L1_DESIGN.md) §4.

## Autonomous execution

Live tenant access is granted via the project's standing operator policy; use
the committed live-smoke harness (`scripts/smoke/smoke.py`) and do not echo
secrets in any output.

## Phase runner harness (workspace-global, default for multi-step phases)

Any multi-step phase work in this repo (≥2 file edits, OR a gate run, OR a
commit-message draft — i.e. most sprints, including every MSP P0/P1/P2 commit)
routes through the workspace-global harness rather than hand-written Codex
prompts:

```bash
bash ~/.cursor-daybook-sync/scripts/phase_runner.sh /path/to/phase-spec.yaml [--auto-commit]
```

Spec template (with a worked MSP P2 example):
`~/.cursor-daybook-sync/scripts/templates/phase_spec.example.yaml`

Usage doc + spec field reference + exit codes:
`~/.cursor-daybook-sync/scripts/templates/phase_runner.README.md`

The harness owns prompt rendering, preflight (scope sanity, git clean), Codex
launch, marker polling, regression gates, commit-message draft, JOURNAL-entry
draft, and optional `--auto-commit` + push. Output is a `PHASE_RUNNER_RESULT`
block with `OVERALL=green|amber|red` plus `VERIFIER_RECOMMENDED=yes|no`.

**Do not** invent an SDK-local copy of the harness — it lives workspace-global
so the same discipline binds across `declarative-sdk-for-k`,
`keeper-vault-rbi-pam-testenv`, and any sibling repo. Hand-written ad-hoc
Codex prompts for multi-step phases are a discipline drift event surfaced by
the workspace-level `token-economy.mdc` audit checklist (#16). Exempt cases:
single one-shot probes, harness-self-modification, and tasks whose spec format
genuinely cannot be captured (escalate the last; the spec format may need
extension).

## Where “orchestration” lives (reconciles in-repo vs workspace)

| Layer | What it is | Canonical location |
|-------|------------|-------------------|
| **Product roadmap + honest gates** | PAM/vault/MSP scope, support labels, live-proof requirements | In-repo: [`docs/SDK_COMPLETION_PLAN.md`](./docs/SDK_COMPLETION_PLAN.md), [`docs/SDK_DA_COMPLETION_PLAN.md`](./docs/SDK_DA_COMPLETION_PLAN.md), [`docs/V2_DECISIONS.md`](./docs/V2_DECISIONS.md), [`RECONCILIATION.md`](./RECONCILIATION.md) |
| **Multi-step worker phases** | YAML spec + gates + commit/JOURNAL drafts; **not** a second harness inside this tree | `bash ~/.cursor-daybook-sync/scripts/phase_runner.sh /path/to/phase-spec.yaml` (see section above) |
| **Sprint memos, Codex prompt bodies, per-session runbooks, daybook excerpts** | Operator coordination; **forbidden** under `docs/` here (see scope-fence) | `~/.cursor-daybook-sync/docs/orchestration/dsk/` |
| **Style / cost / daybook loop** | Preamble, caveman, token-economy, boot scripts | `~/.cursor-daybook-sync/scripts/`, `~/.cursor/skills/AGENT_PREAMBLE.md` (paths in your rules stack) |
| **Merge / release checks (this repo has no in-tree `phase0_gates.sh`)** | Maintainer-run | **`bash scripts/phase_harness/run_local_gates.sh`** (ruff+format+mypy+pytest) or the same commands by hand; optional: `python -m build` + `twine check dist/*` |

If an older doc or chat refers to `docs/ORCHESTRATION_*.md` **inside this repo**, that tree was **removed on purpose** (discipline: delivery repo vs orchestrator repo). Follow the table above instead of recreating those paths (CI will fail on new `docs/ORCHESTRATION_*` adds — `.github/workflows/scope-fence.yml`).

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

### E. Programmatic load (Python: PAM vs vault)

- **PAM (`pam-environment.v1`):** `from keeper_sdk.core import load_manifest, build_graph, compute_diff, build_plan, …` — see [`README.md`](./README.md) § Programmatic use.
- **`keeper-vault.v1`:** use **`load_declarative_manifest`** (returns `VaultManifestV1`), **`build_vault_graph`**, **`compute_vault_diff`**, **`vault_record_apply_order`**, then **`build_plan`** + provider — same exit-code / marker patterns as CLI. **`load_manifest` is PAM-only** and refuses vault documents.
- **Reference:** [`keeper_sdk/core/manifest.py`](./keeper_sdk/core/manifest.py) module docstring; offline round-trip tests in [`tests/test_vault_mock_provider.py`](./tests/test_vault_mock_provider.py).

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
5. **Never add operator-side orchestration narrative under `docs/`.** Sprint memos, codex prompts, sprint-to-sprint orchestration plans, daybook excerpts → daybook repo (`~/.cursor-daybook-sync/docs/orchestration/dsk/`), not this repo. Public SDK `docs/` is for end-user docs only. Scope-fence catches the obvious cases; this rule catches what regex misses.

## Operator tooling

Operator-side orchestration tooling is not part of this SDK and is not
documented here.

Inside this repo, the binding contracts agents read are:

- The exit-code table above + `docs/VALIDATION_STAGES.md`.
- `docs/SDK_DA_COMPLETION_PLAN.md` — devil's-advocate completion gates;
  classifies every modeled capability as `supported` / `preview-gated` /
  `upstream-gap`. Wins over wish-list roadmaps.
- `docs/SDK_COMPLETION_PLAN.md` — long-form roadmap + risk gates.
- `scripts/smoke/README.md` — committed live-smoke harness contract.

## Where to read next

- `README.md` — human-oriented overview.
- `docs/COMMANDER.md` — pinned Commander version + capability matrix.
- `docs/SDK_DA_COMPLETION_PLAN.md` — devil's-advocate completion gates.
- `docs/SDK_COMPLETION_PLAN.md` — long-form completion roadmap.
- `docs/LOGIN.md` — custom-helper contract.
- `V1_GA_CHECKLIST.md` — roadmap toward v1.0.0 GA.
- `AUDIT.md` — milestone history + reconciliation with the upstream DOR.
- `REVIEW.md` — devil's-advocate review notes (what was deferred, why).
