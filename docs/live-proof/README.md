# Live-proof artifacts (`docs/live-proof/`)

**Audience:** maintainer, agent, or CI **explicitly granted** live access to a
lab tenant for this repo (same bar as [`AGENTS.md`](../AGENTS.md) § Autonomous
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

Example: `keeper-vault.v1.89047920.sanitized.json` (use the first 7–8 hex
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

## V8 prep (not live evidence)

**Template JSON (shape only):** [`keeper-vault.v1.sanitized.template.json`](./keeper-vault.v1.sanitized.template.json) — `template: true`; safe to commit. After a tenant run, produce a real `*.sanitized.json` per the naming rule above, redact, then point `x-keeper-live-proof.evidence` at that file.

**Sample manifest (one `login`):** [`../examples/scaffold_only/vaultOneLogin.yaml`](../examples/scaffold_only/vaultOneLogin.yaml) — edit `uid_ref` / title / field values for your lab folder; keep non-production credentials only.

## Current placeholders

| Family | Schema status | Evidence pointer |
|--------|---------------|------------------|
| `keeper-vault.v1` | `scaffold-only` | Commander L1 + `validate --online` in code; commit a **sanitized** transcript (see template + checklist §6) before `supported` |
| `keeper-vault-sharing.v1` | `scaffold-only` | This README until a transcript lands |
| `keeper-enterprise.v1` | `scaffold-only` | This README until a transcript lands |

When a real file exists, point `evidence` at that file path instead of this
README.

## Live proof sequence

Run one live writer per tenant profile, commit only sanitized transcripts, and
update the relevant schema evidence pointer after the proof passes.
