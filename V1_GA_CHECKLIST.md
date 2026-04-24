# v1.0.0 GA checklist

Derived from the 2026-04-24 devil's-advocate audit (see `AUDIT.md`).
Items are **blocking** unless marked `[hardening]`. Check them off in
PRs that close them so the next agent can tell at a glance what's left.

## Shipping gates

### 1. Capability parity with the schema
- [ ] Decision: implement OR shrink-schema. Default recommendation is
      **shrink** — add `x-preview` on `rotation_settings`,
      `jit_settings`, `gateway.mode: create`, top-level `projects[]`.
      Validation rejects them unless `DSK_PREVIEW=1`.
- [ ] Examples under `examples/` must run clean against
      `--provider commander` with no preview flag.
- [ ] `pam_configuration_uid_ref` linking implemented OR marked
      preview with a stub.
- [ ] Upstream DOR `keeper-pam-declarative/` updated to remove the
      mismatched schema surface.

### 2. Upstream DOR reconciliation
- [ ] Merge `keeper-pam-declarative/NOTES_FROM_SDK.md` contradictions
      upstream (7 items):
  - [ ] Marker wire format doc vs code
  - [ ] `pam project export/remove` non-existence — update DOR docs
  - [ ] Exit code 2 overloading — one source of truth
  - [ ] `pamRemoteBrowser` session-recording field mapping
  - [ ] `KEEPER_SDK_LOGIN_HELPER` documented in `DELIVERY_PLAN.md`
  - [ ] Commander version pin in `DELIVERY_PLAN.md`
  - [ ] DOR-internal doc-pair (`METADATA_OWNERSHIP.md` vs
        `docs/keeper-io/.../reference/marker.md`) reconciled

### 3. CI + release plumbing
- [x] MIT `LICENSE`, `CHANGELOG.md`, `SECURITY.md`.
- [x] GitHub Actions: ruff + mypy + pytest 3.11/3.12/3.13.
- [x] `pyproject.toml` pins `keepercommander>=17.2.13,<18`.
- [ ] First green CI run on `main`.
- [ ] PyPI publish workflow (`on: release: published`) gated by a
      protected `pypi-publish` environment with an OIDC trusted
      publisher — no API tokens in repo secrets.
- [ ] Signed release tag `v1.0.0` with `gh release create`.

### 4. Login path usability
- [x] Ship `EnvLoginHelper` as in-tree reference.
- [x] `KEEPER_SDK_LOGIN_HELPER` now optional; env-var fallback kicks in.
- [x] `docs/LOGIN.md` with the 30-line skeleton.
- [ ] At least one live-smoke run that uses `EnvLoginHelper` (not the
      workstation-local `deploy_watcher.py`).

### 5. `validate --online` completeness
- [ ] Stage 5 actually verifies pam_configuration presence,
      shared-folder reachability, KSM app binding. Today it only
      prints a plan summary.
- [ ] Documented exit codes for each stage failure.

### 6. Live-smoke coverage
- [x] `pamMachine` create → verify → delete cycle.
- [ ] `pamDatabase` cycle.
- [ ] `pamDirectory` cycle.
- [ ] `pamUser` cycle.
- [ ] `pamRemoteBrowser` cycle.
- [ ] Adoption path against unmanaged records.
- [ ] Field-drift → UPDATE path.
- [ ] Two-writer conflict (ownership-marker race).

## Hardening (non-blocking but tracked)

- [ ] Remove unused `DeleteUnsupportedError` OR wire it as a narrower
      exception than `CapabilityError`.
- [ ] Read `gateway.ksm_application_name` in `reference_existing`
      mode (currently parsed and dropped).
- [ ] Snapshot tests for `RichRenderer` table layouts.
- [ ] Expand `redact()` patterns (bearer tokens, JWTs, KSM URLs).
- [ ] `tests/test_perf.py` → add `resource.getrusage` memory
      assertions (currently prints only).
- [ ] Map DOR `TEST_PLAN.md` scenarios to SDK tests (~6 still zero-cov:
      adoption race, partial-apply rollback, KSM rotation mid-apply,
      Commander version mismatch, stale marker cleanup, two-writer).
- [ ] Module rename from `keeper_sdk` → `declarative_sdk_k` (breaking, v2.0.0;
      will ship a shim module so `import keeper_sdk` keeps working for
      one minor cycle).

## Release gating

A PR can tag v1.0.0 when every `[ ]` in "Shipping gates" above is
checked **and** CI is green on `main` for two consecutive merges. The
"Hardening" section does not gate the tag; track via GitHub Issues.
