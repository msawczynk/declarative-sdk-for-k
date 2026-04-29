# declarative-sdk-for-k

> `dsk` — a declarative, agent-first SDK for Keeper tenant state.
> **Production today (PAM bar):** `pam-environment.v1` — full
> `validate` / `plan` / `apply` / `discover` on mock + Commander for the
> PAM lifecycle (machines, databases, directories, nested users, remote
> browsers, shared folders, gateways, configurations). Rotation settings, JIT,
> gateway `mode: create`, and RBI tuning are split by proof: nested
> `resources[].users[].rotation_settings` is supported on Commander 17.2.16+;
> top-level/resource rotation, JIT, gateway `mode: create`, and dirty RBI fields
> stay gated or upstream-gap.
>
> **Other manifest families** (`keeper-vault`, `keeper-enterprise`, …) ship as
> **packaged JSON Schema** for design, CI, and agent ergonomics; they are **not**
> “GA like PAM” until they pass the same gates (typed core, provider wiring, live
> proof). See [**Readiness vs the PAM bar**](#readiness-vs-the-pam-bar) and
> [`docs/PAM_PARITY_PROGRAM.md`](docs/PAM_PARITY_PROGRAM.md) for the program that
> lifts scaffolds to full support. The README hero will only claim universal GA
> after that program completes — not when schemas land alone.

Pure-Python core, no network I/O until you reach a provider. Machine-
readable everywhere (`--json`, typed exit codes, `next_action` on
every error). Designed so an LLM agent can plan, apply, and recover
from failure without a human in the loop.

**If you are an agent or LLM**: start at [`AGENTS.md`](AGENTS.md) for the
command table, exit-code contract, JSON shapes, **where multi-session
orchestration lives** (phase runner, [`daybook harness`](scripts/daybook/README.md)
from a clone, in-repo vs out-of-repo), and guardrails. Scoped completion contracts live in
[`docs/SDK_DA_COMPLETION_PLAN.md`](docs/SDK_DA_COMPLETION_PLAN.md)
and [`docs/SDK_COMPLETION_PLAN.md`](docs/SDK_COMPLETION_PLAN.md).

### Progress snapshot (2026-04)

Already on **`v1.3.0` / `main`** (see **[`CHANGELOG.md`](CHANGELOG.md)** [**1.3.0**] for detail):

- **P2.1 / GH#4 (nested rotation):** Commander 17.2.16 adds `pam rotation list --record-uid --format json`; the SDK now hydrates nested `pamUser.rotation_settings` on discover and defaults the nested `resources[].users[]` apply path on. Top-level users, resource-level rotation, and `default_rotation_schedule` remain blocked.
- **Exports / RBI:** `pamRemoteBrowser` discover maps **`rbiUrl` ↔ manifest `url`**; docs smoke README + **COMMANDER** RBI buckets aligned with DA Phase 3 evidence targets.
- **Phase 7:** KSM bootstrap is live-proven, the KSM inter-agent bus is a sealed stub, shared-folder Commander create/update/membership wiring is offline-proven with destructive-change guards, and MSP discover/validate is wired while Commander MSP mutation stays unsupported.
- **Operator ergonomics:** [`AGENTS.md`](AGENTS.md) documents **`git bundle`** handoff when **`git push`** fails from a sandboxed shell; [`scripts/phase_harness/bundle_unpushed_commits.sh`](scripts/phase_harness/bundle_unpushed_commits.sh) creates the bundle.
- **Orchestration (workspace):** `queue_runner.sh` in the operator’s **`~/.cursor-daybook-sync/scripts/`** tree chains **`phase_runner.sh`** queue items; **`--live`** + **`--env-file`** pair with **`ksm_creds.sh`** for Codex **`live_smoke`** profile (see **`queue_runner.README.md`** next to that script). Two lab identities — general Acme lab vs MSP parent — use separate **KSM** record pointers; operator-only env templates such as **`~/Downloads/dsk-queue.live.env`** / **`dsk-queue-msp.live.env`** stay outside this repo.
- **MSP family:** **`msp-environment.v1`** schema + registry on **`main`**; mock **`import`** adoption path + **`validate --online`** discover (`CommanderCliProvider`); **Commander apply/import for MSP** still unsupported — [`docs/MSP_FAMILY_DESIGN.md`](docs/MSP_FAMILY_DESIGN.md), [`docs/V2_DECISIONS.md`](docs/V2_DECISIONS.md) Q5.

## Capability scope

| Area                 | v1.3.0 coverage                        | Roadmap                      |
|----------------------|----------------------------------------|------------------------------|
| PAM resources        | machines, databases, directories, nested users, remote-browsers; nested `resources[].users[].rotation_settings` on Commander 17.2.16+ | standalone/top-level users, JIT, resource-level rotation, gateway `mode: create` |
| Gateways             | `reference_existing` mode            | `create` mode                |
| Shared folders       | typed model, MockProvider lifecycle, Commander create/update/membership wiring, `--allow-delete` guards for destructive membership changes | live second-account readback proof before full sharing support |
| KSM applications     | reference_existing + share-bindings; **`dsk bootstrap-ksm` provisions an app + admin-record share + one-time client token + redeemed `ksm-config.json`**; `KsmLoginHelper` pulls Commander credentials *from* KSM (close the loop). Phase B inter-agent bus API is sealed (`secrets/bus.py` raises `CapabilityError` / `NotImplementedError`). | declarative app lifecycle; client-token rotation; bus client implementation |
| Ownership markers    | read + write + adopt                 | multi-manager arbitration    |
| Vault records (non-PAM) | typed-model read/write via `login` resource | generic records, file records |
| Teams / roles        | discover surface only                | full declarative lifecycle   |
| MSP / enterprise config | `msp-environment.v1` schema + Commander `validate --online` discover for MSP admin sessions; Commander MSP import/apply unsupported | SSO, SCIM, richer nodes, MSP mutation contract |
| Compliance / audit   | read-only `dsk report password-report` and `security-audit-report` live-proven; `compliance-report --rebuild` has JSON-envelope proof but no-rebuild stays gated | extra report verbs; **no** posture-as-manifest (V2) |

The schema stays stable across capability additions — new top-level
blocks join `pam-environment.v1` rather than bumping the version. See
[`V1_GA_CHECKLIST.md`](V1_GA_CHECKLIST.md) for the commitment list
gating the `1.0.0` tag.

## Readiness vs the PAM bar

“**Ready like PAM**” means more than a JSON file: typed models, Commander-backed
discover/plan/apply, tests, live proof, and matrix alignment — see
[`docs/PAM_PARITY_PROGRAM.md`](docs/PAM_PARITY_PROGRAM.md). **Do not** treat
packaged schema alone as GA.

| Manifest family (`schema:` key) | Schema in repo | Clears PAM bar today |
|----------------------------------|----------------|----------------------|
| `pam-environment.v1` | yes | **Yes** (PAM scope; preview-gated sub-features called out in AGENTS / checklist) |
| `keeper-vault.v1` | yes | **No** — `scaffold-only` live proof + matrix bar; **yes** L1 Commander slice (`login` discover/apply **UPDATE** on **record version 3** JSON), `validate --online`, and semantic `plan`/`diff` for scalar `login` `fields[]` vs Commander-flattened payloads (see **Honest limits** below) |
| `keeper-vault-sharing.v1` | yes | **No** — scaffold-only |
| `keeper-enterprise.v1` | yes | **No** — scaffold / partial design only |
| `msp-environment.v1` | yes | **No** — Commander discover/validate is supported, Commander import/apply is not implemented |
| `keeper-integrations-identity.v1` | yes | **No** — scaffold-only |
| `keeper-integrations-events.v1` | yes | **No** — scaffold-only |
| `keeper-ksm.v1` | yes | **No** — KSM bootstrap + helpers exist; declarative family not wired end-to-end |
| `keeper-pam-extended.v1` | yes | **No** — stubs / upstream gaps until Commander paths graduate |
| `keeper-epm.v1` | yes | **No** — watchlist per V2 Q5 |
| `keeper-security-posture.v1` | yes (trap) | **N/A** — `dropped-design`; use `dsk report` verbs |

Separate runtime: **`dsk report`** verbs are not manifest families. In v1.3.0,
`password-report` and `security-audit-report` are live-proven production read
paths; `compliance-report` remains preview-gated for the no-rebuild cache shape
until Commander returns JSON or the wrapper handles that empty-output case.

### Honest limits — vault L1 (devil’s-advocate bar)

Treat the vault row above as **“wired + tested,” not “proven like PAM”**
until **G6** (sanitized live transcript + matrix) and **§7** sign-off on
[`docs/VAULT_L1_DESIGN.md`](docs/VAULT_L1_DESIGN.md) land.

- **Semantic diff:** compares flattened **scalar** login values; duplicate
  labels, non-scalar typed fields, or Commander shape drift across versions can
  still produce false “clean” or surprise **UPDATE** — extend tests when you
  hit real records.
- **Apply:** Commander **vault UPDATE** uses the **version 3** JSON edit path;
  older record shapes are out of scope until explicitly supported. Confirm
  failures are not silent (stderr / return contract) in your environment
  before unattended automation.
- **`validate --online`:** bundles discover, binding gates, and diff; network
  or Commander flakes fail a check that offline `validate` would pass — use
  offline CI for schema-only gates and reserve `--online` for integration
  slots.
- **Secrets in JSON:** `--json` can echo titles, UIDs, and folder scope; pipe
  and log discipline still matter (`docs/live-proof/README.md`).

See [`AGENTS.md`](AGENTS.md) for the agent operating manual.
Integrator detail: [`docs/VAULT_L1_DESIGN.md`](docs/VAULT_L1_DESIGN.md) §4 (semantic diff, races, UPDATE).

## Keeper Security Platform: what DSK does not cover (by design)

The Keeper Security Platform includes Commander surfaces that **stay
outside** declarative `dsk apply` and, for many categories, outside
wrapped `dsk report` / `dsk run` until an explicit product decision
re-opens them. That is intentional boundary, not a missing Commander
feature. Canonical rationale: [`docs/V2_DECISIONS.md`](docs/V2_DECISIONS.md)
(Q1 posture drop, Q3 runtime scope, Q5 MSP/EPM, and the out-of-scope block).

| Platform capability | Typical Commander / product surface | Why DSK does not touch it | What to use instead |
|---------------------|--------------------------------------|---------------------------|---------------------|
| Posture as declarative state | BreachWatch posture, compliance baselines, continuous audit as a manifest family | **P15 dropped-design** — surfaces are read-only / one-shot; remediation is per-record user action, not an idempotent manifest reconcile (V2 Q1). | Shipped: `dsk report password-report`, `compliance-report`, `security-audit-report`. Still Commander-direct until wrapped at the same bar: e.g. `breachwatch-list`, richer `enterprise-reports`. |
| MSP / distributor | MSP tree, `msp-info`, managed-company lifecycle | **In scope for declarative MSP** as of 2026-04-27 (V2 Q5): parent lab tenant + design memo `docs/MSP_FAMILY_DESIGN.md`; first slice `msp-environment.v1` — not GA like PAM until live-proof + matrix bar. | Commander today for undeclared paths; `dsk validate --online` MSP arms when wired; lab harness `keeper-vault-rbi-pam-testenv/scripts/msp_smoke.py` for read-only envelopes. |
| Auth factor enrollment | `two_fa` enrollment-style flows | **Q3** — out of scope for both `dsk run` and `dsk report` until reversed. | Commander direct. |
| Vault repair / migration | `verify_records`, `convert` | **Q3 + V2 out-of-scope** — explicit non-goals for v2.0+. | Commander direct. |
| Debug / graph writers | `pam_debug` and similar | **Q3** — not treated as end-user SDK surface. | Commander direct. |
| Live privileged sessions | `connect`, tunnels, supershell, ssh-agent, interactive PAM launch | Mutating / TTY session semantics (**Q3 `dsk run` bucket**); never modeled as `dsk apply` state. | Commander today; possible future `dsk run` passthrough — still not manifest lifecycle. |
| Full EPM / PEDM control plane | PEDM deployments, agents, policies, collections | **P16 watchlist** — gated on source audit + EPM customer + licensed tenant smoke (Q5). | Commander until triggers clear; schema stays roadmap-only. |

For how much of Commander is mapped into docs and CI drift checks, see
[`docs/CAPABILITY_MATRIX.md`](docs/CAPABILITY_MATRIX.md) and
[`docs/capability-snapshot.json`](docs/capability-snapshot.json).

## Layout

```
keeper_sdk/                          # import path stable through 1.x
                                     # (renamed to declarative_sdk_k in 2.0 with a shim)
  core/                              # pure models, schema, graph, diff, planner, metadata, redact
    schemas/                         # pam-environment.v1.schema.json + per-family dirs (see PAM bar)
  providers/                         # MockProvider, CommanderCliProvider
  auth/                              # LoginHelper protocol + EnvLoginHelper / KsmLoginHelper reference impls
  secrets/                           # KSM as first-class SDK feature: bootstrap.py (Commander-driven
                                     # provisioning), ksm.py (KsmSecretStore + load_keeper_login_from_ksm),
                                     # bus.py (Phase B inter-agent bus directory — sealed skeleton)
  cli/                               # `dsk` (validate / export / plan / diff / apply / import / bootstrap-ksm)
tests/                               # run `pytest` — ~518 tests collected; CI ratchets coverage
examples/
  SCAFFOLD.md                        # PAM root YAMLs + scaffold_only; CI validate vs mock-plan split
docs/
  VAULT_L1_DESIGN.md                 # vault L1 scope / §4 caveats; §7 sign-off pending (G2 ◐)
  PAM_PARITY_PROGRAM.md              # Definition of Done + phases to full support (not scaffold)
  V2_DECISIONS.md                    # schema families, runtime scope, MSP/EPM, explicit non-goals
  CAPABILITY_MATRIX.md               # Commander roots vs DSK buckets (synced from scripts/sync_upstream.py)
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
pip install git+https://github.com/msawczynk/declarative-sdk-for-k.git@v1.3.0
```

Requires Python 3.11+. `keepercommander>=17.2.16,<18` is pulled in
automatically — only exercised when you hit the `commander` provider;
the mock provider works standalone.

## Quick start (offline, mock provider)

```bash
dsk validate examples/pamMachine.yaml
dsk --provider mock plan examples/pamMachine.yaml --json
dsk --provider mock apply examples/pamMachine.yaml --auto-approve
```

Any packaged manifest family (`schema: keeper-vault.v1`, …) can run
`dsk validate` for **JSON Schema + dropped-design guard**. **`--online`** is
**PAM** for full tenant binding + diff smoke, and **`keeper-vault.v1`** when you
use **`--provider commander`** with a scoped folder (`--folder-uid` or
`KEEPER_DECLARATIVE_FOLDER`) — see [`AGENTS.md`](AGENTS.md) and
[`docs/VALIDATION_STAGES.md`](docs/VALIDATION_STAGES.md). Other families stay
offline until their provider slice ships (`docs/PAM_PARITY_PROGRAM.md`).
Use **`dsk validate PATH --json`** for a single JSON object (`mode` varies by
family — e.g. `schema_only`, `pam_full`, `vault_offline`, `vault_online`) for
agents and CI parsers.

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
live-proven on the bootstrap/login path and is the recommended production
helper once `dsk bootstrap-ksm` has produced a config. Preview-gated surfaces
such as dirty RBI fields, standalone/top-level `pamUser` rotation, and gateway
`mode: create` still need their own proof before they become support claims.

### Export

`dsk export INPUT.json -o env.yaml` lifts a Commander-shaped PAM project JSON
document into a manifest. Commander 17.2.16 does **not** provide a native
`pam project export` command; operators produce the JSON by a supported
Commander/project export helper or by iterating `keeper get` / `keeper ls`, and
`dsk export` reads that file path.

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

## Status (v1.3.0, 2026-04-29)

Core + mock: complete. Commander provider: discover, plan, apply
(create / update / delete via `keeper rm`, gated behind
`--allow-delete`), ownership-marker read/write, provider-level
capability check. **`keeper-vault.v1` L1** adds Commander discover/apply
(including **login UPDATE** on v3 JSON), **`dsk validate --online`** for
vault, and semantic vault diff for scalar logins — still **not** “PAM-bar
GA” until live proof and the readiness gates in
[`docs/PAM_PARITY_PROGRAM.md`](docs/PAM_PARITY_PROGRAM.md) are complete.
Capability gaps (top-level/resource rotation, JIT, gateway `mode: create`)
surface as plan-time CONFLICT rows rather than silent drops, so the CLI's
`plan` and `apply --dry-run` agree before any mutation runs.
KSM is now a first-class SDK feature: `dsk bootstrap-ksm` provisions an
app + share + client token + `ksm-config.json` end-to-end, and
`KsmLoginHelper` reads Commander credentials back out of that vault — so
the SDK can authenticate without any plaintext env vars on the host. The KSM
bus surface is a documented sealed stub, not publish/subscribe support.
Current local gate: **1047 passed / 2 skipped / 1 xfailed**. Live
`EnvLoginHelper` smoke proved full apply for `pamMachine`; P3 RBI proof is
bucketed in `docs/COMMANDER.md`; nested `resources[].users[].rotation_settings`
is supported on Commander 17.2.16+ while top-level users and default rotation
schedules remain blocked.

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

For **`keeper-vault.v1`**, use **`load_declarative_manifest`**, **`build_vault_graph`**,
**`compute_vault_diff`**, and **`vault_record_apply_order`** with **`build_plan`** and a
provider (same `MockProvider` / `CommanderCliProvider` pattern). See
[`tests/test_vault_mock_provider.py`](tests/test_vault_mock_provider.py) and
[`AGENTS.md`](AGENTS.md). **`load_manifest`** stays **PAM-only** and rejects vault documents.

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
