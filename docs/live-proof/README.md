# Live-proof artifacts (`docs/live-proof/`)

**Audience:** maintainer, agent, or CI **explicitly granted** live access to a
lab tenant for this repo (same bar as [`AGENTS.md`](../../AGENTS.md) § Autonomous
execution). Read this before changing `x-keeper-live-proof.status` on a family
schema.

**Normative rules:** `keeper_sdk/core/schemas/CONVENTIONS.md` (block shape,
`since_pin` = full 40-char SHA from `.commander-pin`). Meta schema:
`keeper_sdk/core/schemas/_meta/x-keeper-live-proof.schema.json`.

**Vault L1 semantics (before interpreting a vault transcript):** [`VAULT_L1_DESIGN.md`](../VAULT_L1_DESIGN.md) §4 and [`VALIDATION_STAGES.md`](../VALIDATION_STAGES.md) (*Vault — operator caveats*) — scalar diff limits, races, offline vs `vault_online` CI.

**Prerequisite health:** keep smoke/L1 prerequisites aligned with
`scripts/smoke/README.md` and use the committed smoke harness for live proof.

## Live access for code

Agents or CI may hold the L1 gate **when**:

- The maintainer has granted **standing or per-run** permission (see
  `AGENTS.md`, or a task body that lists exact argv / scenarios and tenant
  scope).
- The actor uses **committed** harnesses or documented CLI steps — not
  exploratory shell on the tenant.
- Raw capture stays **out of git** until sanitized; the same rules as
  `dsk report` / `secret_leak_check` apply to anything that lands in the repo.

**Concurrency:** one writer per profile per tenant, when profiles use disjoint
Commander config paths, test users, shared folders, KSM apps, and project
names. The smoke harness enforces this via per-profile lock files when
`--parallel-profile` is set; without `--parallel-profile`, the legacy
single-writer-per-tenant rule still applies.

## Naming convention (committed files only)

After sanitization, prefer:

```text
docs/live-proof/<family>.v<major>.<commander-pin-abbrev>.sanitized.json
```

Example: `keeper-vault.v1.91119c4.sanitized.json` (use the first 7–8 hex
chars of the pin for humans; `since_pin` in the schema stays **full 40**).

Use `.sanitized.` in the basename so reviewers grep for it in PRs.

## What “sanitized” means

Nothing in the committed artifact may recover:

- Passwords, TOTP seeds, PEM / private keys, session tokens, or config blobs
- Values of `KEEPER_PASSWORD`, `KEEPER_TOTP_SECRET`, or similar env echoes

Use the same discipline as `dsk report` / `secret_leak_check` and the live
transcript helpers (`keeper_sdk.cli._live.transcript`). When in doubt, keep
**structure and lengths** (e.g. `"password": "<redacted>"`) not literal secrets.

## L1 execution checklist (human or granted automation)

1. **Branch** off current `main`; note `.commander-pin` SHA (full 40) in the
   sprint log.
2. **Run** the smallest scenario that exercises the schema family (see
   `scripts/smoke/README.md` when a scenario exists; otherwise a one-off
   `dsk plan` / `dsk validate --online` path documented in the PR).
3. **Capture** stdout/stderr to a scratch file **outside** the repo (or in
   `.gitignore`); never push raw.
4. **Redact** into the naming pattern above; run `python3 -m json.tool` on JSON
   artifacts before commit (strict RFC 8259).
5. **Grep** the artifact for `BEGIN`, `PRIVATE`, long base64 runs, and any lab
   hostname/email you used — fix until clean.
6. **Commit** artifact + update the family schema:
   - `x-keeper-live-proof.status` → `supported` (or `preview-gated` if gated by
     `DSK_PREVIEW=1` per SDK_DA).
   - `x-keeper-live-proof.evidence` → repo-relative path to this directory.
   - `since_pin` → exact `.commander-pin` line.
7. **Open PR** with a one-line “clean re-plan” or equivalent proof statement in
   the description (SDK_DA completion gates).

## Vault L1 template + sample

**Live evidence:** [`keeper-vault.v1.91119c4.sanitized.json`](./keeper-vault.v1.91119c4.sanitized.json) — `vaultOneLogin` through the committed smoke harness; create -> verify -> clean re-plan -> destroy -> empty re-discover. Interpret it with the scalar `login` limits and race caveats in [`VAULT_L1_DESIGN.md`](../VAULT_L1_DESIGN.md) §4.

**Template JSON (shape only):** [`keeper-vault.v1.sanitized.template.json`](./keeper-vault.v1.sanitized.template.json) — `template: true`; safe to commit and reuse for future vault L1 re-runs. After a tenant run, produce a real `*.sanitized.json` per the naming rule above, redact, remove template-only keys, then point `x-keeper-live-proof.evidence` at that file.

**Sample manifest (one `login`):** [`../../examples/scaffold_only/vaultOneLogin.yaml`](../../examples/scaffold_only/vaultOneLogin.yaml) — edit `uid_ref` / title / field values for your lab folder; keep non-production credentials only.

## Current evidence index

| Family | Schema status | Evidence pointer |
|--------|---------------|------------------|
| `keeper-vault.v1` | `supported` (L1 `login` slice) | [`keeper-vault.v1.91119c4.sanitized.json`](./keeper-vault.v1.91119c4.sanitized.json) — `vaultOneLogin` 2026-04-27; scope remains one scalar `login` record per `VAULT_L1_DESIGN.md` §1/§4 |
| `keeper-vault-sharing.v1` | `scaffold-only` / partial proof | [`keeper-vault-sharing.v1.535e03f.folderlifecycle.sanitized.json`](./keeper-vault-sharing.v1.535e03f.folderlifecycle.sanitized.json) — folder lifecycle only; not a full status flip |
| `keeper-enterprise.v1` | `scaffold-only` | This README until a transcript lands |
| `keeper-pam-environment.v1` (RBI slice) | `supported` (E2E smoke) | [`keeper-pam-environment.v1.89047920.rbi.sanitized.json`](./keeper-pam-environment.v1.89047920.rbi.sanitized.json) — `pamRemoteBrowser` 2026-04-28; see also machine transcript |

When a real file exists and covers the family bar, point `evidence` at that file
path instead of this README. Partial transcripts may live here without changing
schema status.

## Live proof sequence

Run one live writer per tenant profile, commit only sanitized transcripts, and
update the relevant schema evidence pointer after the proof passes. When a
committed smoke scenario exists (for example `vaultOneLogin`), that smoke
scenario is the primary proof path; one-off `dsk validate --online` / `plan`
captures are supporting evidence only.
