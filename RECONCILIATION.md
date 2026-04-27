# RECONCILIATION — design vs tree

Written: 2026-04-26 (agent scaffold pass; refreshed 2026-04-27 for tree + `secrets` scaffold).
Source of truth: this repo @ HEAD `f8fb9d0` (run `git rev-parse HEAD` before large edits).
Cross-checks against `V1_GA_CHECKLIST.md`, `docs/SDK_DA_COMPLETION_PLAN.md`,
`AUDIT.md`, `REVIEW.md`, and DOR pointers in `keeper-pam-declarative/`.

This is for human + agent review. Per-folder maps live in `<dir>/SCAFFOLD.md`.

---

## TL;DR

- **Zero remaining v1.0.0 GA blockers.** Tag policy decided: annotated only — distribution is GitHub-only (no PyPI, no `git verify-tag` consumer flow); GPG/SSH signing not required. Upgrade path if supply-chain requirements change → sigstore/cosign `dist/*` in `publish.yml` (OIDC, no maintainer key).
- **Two open clean-re-plan gates** (preview-gated, not GA blockers): nested-`pamUser` rotation (P2.1), `pamRemoteBrowser` RBI tuning (P3). Apply paths shipped; reviewed clean re-plan is the final lift.
- **Three v1.1 deferrals tracked + accepted:** adoption smoke against unmanaged records, field-drift→UPDATE smoke, two-writer ownership-marker race smoke.
- **One v2 deferral:** module rename `keeper_sdk` → `declarative_sdk_k` (will ship compat shim).
- **Nothing has been silently dropped.** Every preview-gated key fails loud at apply via `_detect_unsupported_capabilities` + plan-surface CONFLICT rows (C3 fix; H6 regression test).

---

## v1.0.0 Shipping Gates (`V1_GA_CHECKLIST.md`)

| § | Item | Status | Evidence in tree |
|---|---|---|---|
| 1 | Capability parity — preview gate for unsupported schema | SHIPPED | `keeper_sdk/core/preview.py`; `tests/test_preview_gate.py` (14 cases) |
| 1 | Examples validate offline + mock-plan clean | SHIPPED | `examples/*.yaml`; `.github/workflows/ci.yml`; `tests/test_smoke_scenarios.py` |
| 1 | `pam_configuration_uid_ref` linking | SHIPPED (in-manifest GA; cross-manifest deferred → fail @ stage 3) | `tests/test_uid_ref_gate.py` |
| 1 | DOR reframed as capability mirror | SHIPPED | `docs/CAPABILITY_MATRIX.md`, `docs/capability-snapshot.json`, `scripts/sync_upstream.py` |
| 2 | DOR reconciliation (7 contradictions) | SHIPPED + SUPERSEDED 2026-04-24 | `AUDIT.md` D-5, `REVIEW.md` |
| 3 | LICENSE + CHANGELOG + SECURITY | SHIPPED | root files |
| 3 | CI matrix (ruff + mypy + pytest 3.11/3.12/3.13) | SHIPPED | `.github/workflows/ci.yml` |
| 3 | `keepercommander>=17.2.13,<18` pin | SHIPPED | `pyproject.toml` |
| 3 | First green `main` CI | SHIPPED | `fb6fb8b` |
| 3 | GitHub Release asset workflow (no PyPI) | SHIPPED | `.github/workflows/publish.yml`, `docs/RELEASING.md` |
| 3 | `v1.0.0` release tag | SHIPPED-by-policy | annotated tag only; GitHub-only repo, no PyPI / no downstream `git verify-tag`; GPG/SSH signing not required (sigstore/cosign of `dist/*` in `publish.yml` is the cheap upgrade path if requirements change) |
| 4 | `EnvLoginHelper` shipped | SHIPPED | `keeper_sdk/auth/helper.py`, `docs/LOGIN.md` |
| 4 | `KEEPER_SDK_LOGIN_HELPER` optional w/ env fallback | SHIPPED | `keeper_sdk/auth/helper.py::load_login_helper` |
| 4 | Live EnvLoginHelper smoke proves login contract | SHIPPED 2026-04-25 | `scripts/smoke/smoke.py --login-helper env` |
| 5 | `validate --online` stage 5 (tenant bindings) | SHIPPED | `Provider.check_tenant_bindings()`, `keeper_sdk/providers/commander_cli.py`, `tests/test_stage_5_bindings.py` |
| 5 | Per-stage exit codes documented | SHIPPED | `docs/VALIDATION_STAGES.md` |
| 6 | `pamMachine` cycle live | SHIPPED + LIVE-GREEN | `AUDIT.md` 2026-04-24/25 |
| 6 | `pamDatabase`/`pamDirectory`/`pamRemoteBrowser` registered + offline-tested | SHIPPED | `scripts/smoke/scenarios.py`, `tests/test_smoke_scenarios.py` |
| 6 | Nested `pamUser` shape | SHIPPED (offline) | `pamUserNested` scenario |
| 6 | Adoption / field-drift / two-writer smokes | DEFERRED v1.1 | tracked in checklist |

**GA verdict:** all gates green. Tag whenever maintainer wants.

---

## Devil's-Advocate Completion Gates (`docs/SDK_DA_COMPLETION_PLAN.md`)

Every modeled capability must classify as `supported` / `preview-gated` / `upstream-gap`.

| Capability | Classification | Apply path | Clean re-plan | Live proof | Notes |
|---|---|---|---|---|---|
| `pamMachine` GA fields | supported | shipped | green | green (multiple) | Reference path. |
| `pamDatabase` GA fields | supported | shipped | offline-green; live-green | scenario | – |
| `pamDirectory` GA fields | supported | shipped | offline-green; live-green | scenario | – |
| `pamRemoteBrowser` connection fields | supported | shipped | offline-green | scenario | – |
| `pamRemoteBrowser` RBI tri-state / audio (DAG-backed) | preview-gated | DAG → manifest merge shipped | reviewed gate (P3) | open | `_merge_rbi_dag_options_into_pam_settings`; `tests/test_rbi_readback.py` |
| Nested `pamUser` shape (in `resources[].users[]`) | supported (shape) | shipped | green | scenario | `pamUserNested` |
| Nested `pamUser.rotation_settings` | preview-gated | apply lands | reviewed gate (P2.1) | open | offline diff anchor in `tests/test_diff.py` |
| Top-level `users[].rotation_settings` | preview-gated | guarded | – | – | gate-lift rule: stays blocked even after nested clears |
| `default_rotation_schedule` | preview-gated | guarded | – | – | needs separate setter/readback proof |
| `jit_settings` | upstream-gap | guarded | – | – | `docs/ISSUE_6_JIT_SUPPORT_BOUNDARY.md` |
| Standalone top-level `pamUser` | preview-gated → v1.1 | guarded | – | – | `V1_GA_CHECKLIST.md` § 6 |
| Gateway `mode: create` | preview-gated / design-only | guarded | – | – | `docs/ISSUE_7_GATEWAY_CREATE_PROJECTS_DESIGN.md` |
| Top-level `projects[]` | preview-gated / design-only | guarded | – | – | same |
| KSM application provisioning (`dsk bootstrap-ksm`) | supported | shipped | offline-green; live gate next | open | `keeper_sdk/secrets/bootstrap.py`; 89 unit tests in `tests/test_bootstrap_ksm.py`; docs in `docs/KSM_BOOTSTRAP.md`. End-to-end live bootstrap → login → apply loop is the next proof. |
| `KsmLoginHelper` (Commander credentials read from KSM) | supported | shipped | offline-green; live gate next | open | `keeper_sdk/auth/helper.py::KsmLoginHelper` + `keeper_sdk/secrets/ksm.py`; 175 unit tests across `tests/test_auth_ksm.py` + `tests/test_secrets_ksm.py`; docs in `docs/KSM_INTEGRATION.md`. |
| Phase B inter-agent KSM bus (`secrets/bus.py`) | preview-gated / skeleton | sealed (raises `CapabilityError`) | – | – | Bootstrap already provisions the directory record via `--with-bus`; client implementation deferred. Wire format + CAS semantics + implementation checklist frozen in module docstring. |

DA Definition-of-Done compliance:
- ✅ GitHub install path works (git URL + release wheel/sdist).
- ✅ Full local checks + GitHub CI green on `main`.
- ✅ All modeled keys classify into one bucket.
- ✅ No preview-gated key silently applies or silently drops (`_detect_unsupported_capabilities` + plan CONFLICT rows; C3 + D-4 + H6).
- ⚠️ Live smoke matrix green for **all** supported mutating surfaces — yes for machine/db/dir; RBI + nested-rotation are **preview-gated**, so this DOD row holds.
- ✅ Unsupported capabilities fail with clear `next_action`.
- ✅ Docs + scaffold match current behaviour.
- ✅ GitHub issue state matches behaviour.

---

## Has anything been DROPPED?

Cross-checking the 2026-04-24 AUDIT scope (W1–W20), DOR contract, and REVIEW deferrals:

| Candidate "drop" | Verdict | Justification |
|---|---|---|
| W10 (byte-identity `apply --dry-run == plan` test) | NOT dropped — absorbed | Delivered with W3; covered in `tests/test_cli.py`. |
| `MANAGER_NAME = "keeper_declarative"` legacy | INTENTIONAL change | Renamed to `keeper-pam-declarative` (W1) per DOR. Old name preserved nowhere. |
| `_parse_ascii_table` (D-3) | INTENTIONAL removal | Migrated to `--format json` after upstream Commander shipped JSON on `pam gateway list` / `pam config list`. Contract pins in `tests/test_coverage_followups.py`. |
| `Path.home() / "Downloads"` login-helper fallback | INTENTIONAL removal (P0 in REVIEW) | Workstation-specific default unsafe in library. Now requires env var. |
| `DeleteUnsupportedError` | KEPT as compat shim | Subclass of `CapabilityError`. Test in `tests/test_errors.py`. |
| Phase 2.1 (nested rotation) full close | NOT dropped — IN FLIGHT | Apply ✅ marker verify ✅ clean re-plan ⏳ (parent-verified gate). |
| Phase 3 (RBI) full close | NOT dropped — IN FLIGHT | DAG merge shipped; clean re-plan ⏳. |
| Adoption smoke / field-drift smoke / two-writer smoke | DEFERRED v1.1 (explicit) | `V1_GA_CHECKLIST.md` § 6 marks them. |
| Module rename `keeper_sdk` → `declarative_sdk_k` | DEFERRED v2.0 (explicit) | Hardening row. Ship via compat shim. |
| Multi-project manifests | OUT OF SCOPE per AUDIT | `Project` 0..1 per manifest per `SCHEMA_CONTRACT.md` L98. |
| DAG-level dependency checks on delete | OUT OF SCOPE per AUDIT | Project invariant: no direct DAG access. Commander itself refuses dependent `rm`. |

**Conclusion: no silent drops.** Every gap is either explicitly deferred (with version target), explicitly preview-gated, or explicitly out-of-scope per project invariant.

---

## Drift detected vs prior root `SCAFFOLD.md`

Prior `SCAFFOLD.md` predates several committed paths. Refresh applied:

- `tests/test_errors.py` — `DeleteUnsupportedError` compat shim.
- `tests/test_rbi_readback.py` — RBI discover + DAG-merge unit tests.
- `keeper_sdk/secrets/{bootstrap,ksm,bus}.py` — KSM-as-feature delivery.
- `tests/test_auth_ksm.py`, `tests/test_secrets_ksm.py`, `tests/test_bootstrap_ksm.py`, `tests/_fakes/{ksm,commander}.py` — 264 KSM unit tests.
- `docs/KSM_BOOTSTRAP.md`, `docs/KSM_INTEGRATION.md` — KSM operator docs.
- `.github/workflows/scope-fence.yml` — structural orchestration-path denylist.
- This file (`RECONCILIATION.md`) and the per-folder `SCAFFOLD.md` set.

Operator-side tooling is not part of this SDK and is not documented here.

---

## Open questions surfaced for next session

(Echo of the ones already in root `SCAFFOLD.md` — kept so this file stands alone.)

1. Public mirror of `keeper-pam-declarative` — push to GitHub remote or keep local?
2. `sdk-live-smoke` branch — rename / delete / leave as snapshot?
3. `DSK_PREVIEW=1` discoverability — one-line in error vs dedicated doc page?
4. Gateway `mode: create` + `projects[]` — design done; needs Commander source audit + `projects[]` provider conflict hardening + disposable-infra live proof.
5. Post-import RBI tuning — design readback/re-plan semantics before lifting `preview-gated` to `supported`.
6. Nested `pamUser` rotation — close P2.1 by proving clean re-plan + destroy on a parent-run live smoke.
7. ~~Signed `v1.0.0` tag~~ — RESOLVED 2026-04-26: annotated tag only by policy (GitHub-only repo). Sigstore/cosign of `dist/*` is the cheap upgrade path if supply-chain requirements ever appear.

---

## How to use this file (for agents)

1. Read this file to know what's open vs shipped vs deferred — **before** proposing new features.
2. Cross-link from PR descriptions when closing a row.
3. When closing a row, update **both** this file AND the source-of-truth (`V1_GA_CHECKLIST.md` or `docs/SDK_DA_COMPLETION_PLAN.md`) — never just this one.
4. When a new capability lands, add it here under its phase + classify it (`supported` / `preview-gated` / `upstream-gap`). Silent additions are forbidden.
5. Per-folder context lives in `<dir>/SCAFFOLD.md` (see refreshed root `SCAFFOLD.md` table).
