# Live-proof artifacts (`docs/live-proof/`)

**Audience:** maintainer, **or** any agent / automation **explicitly granted**
live access to a lab tenant for this repo (same bar as
[`AGENTS.md`](../AGENTS.md) § Autonomous execution). Read this before changing
`x-keeper-live-proof.status` on a family schema.

**Normative rules:** `keeper_sdk/core/schemas/CONVENTIONS.md` (block shape,
`since_pin` = full 40-char SHA from `.commander-pin`). Meta schema:
`keeper_sdk/core/schemas/_meta/x-keeper-live-proof.schema.json`.

## Live access for code (agents, workers, CI)

Live proof is **not** parent-only. Code may hold the L1 gate **when**:

- The maintainer has granted **standing or per-sprint** permission (see
  `AGENTS.md` — smoke harness, or a task body that whitelists exact argv /
  scenarios and tenant scope).
- The actor uses **committed** harnesses or documented CLI steps — not
  exploratory shell on the tenant.
- Raw capture stays **out of git** until sanitized; the same rules as
  `dsk report` / `secret_leak_check` apply to anything that lands in the repo.

**Concurrency:** still **one live session / writer lane per tenant at a time**
(human or automation). Two parallel agents against the same tenant without
coordination is out of scope — use a lock, a queue, or different tenants.

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

## Current placeholders

| Family | Schema status | Evidence pointer |
|--------|---------------|------------------|
| `keeper-vault.v1` | `scaffold-only` | This README until a transcript lands |
| `keeper-vault-sharing.v1` | `scaffold-only` | This README until a transcript lands |

When a real file exists, point `evidence` at that file path instead of this
README.

## Parallel orchestration

See `docs/NEXT_SPRINT_PARALLEL_ORCHESTRATION.md` — **R4** is the prep that feeds
**L1** (serial **per tenant**: one actor at a time, human or granted code) then
**F3** (schema pointer + artifact commit).
