# RECONCILIATION — design vs tree

Written: 2026-04-26 (agent scaffold pass; refreshed 2026-04-29 for KSM live + rotation/RBI + P2.1 `diff` queue + v1.1 offline quality smokes + v1.2/Phase 7 entry/final pass + v1.3.0 release + P13 KSM bus preview).
Source of truth: `main` at time of last doc edit (exact SHA: `git rev-parse HEAD`).
Cross-checks against `V1_GA_CHECKLIST.md`, `docs/SDK_DA_COMPLETION_PLAN.md`,
`AUDIT.md`, `REVIEW.md`, and DOR pointers in `keeper-pam-declarative/`.

This is for human + agent review. Per-folder maps live in `<dir>/SCAFFOLD.md`.

---

## TL;DR

- **Zero remaining v1.0.0 GA blockers.** Tag policy decided: annotated only — distribution is GitHub-only (no PyPI, no `git verify-tag` consumer flow); GPG/SSH signing not required. Upgrade path if supply-chain requirements change → sigstore/cosign `dist/*` in `publish.yml` (OIDC, no maintainer key).
- **GH #35 resolved in Commander 17.2.16:** nested-`pamUser` rotation readback is unblocked by `pam rotation list --record-uid --format json`; the SDK now hydrates nested `pamUser.rotation_settings` during discover. **P3 / #5** `pamRemoteBrowser` closeout evidence is doc-ready (2026-04-28 smoke + COMMANDER P3.1 + DA Phase 3); dirty/list/audio subfields stay bucketed.
- **v1.3.0 release:** Phase 7 hardening is cut on `main`: Commander 17.2.16 floor, nested `resources[].users[].rotation_settings` default-enabled, shared-folder write primitives + destructive guards, KSM bootstrap live proof, KSM bus preview implementation, MSP discover/validate, and report caveats.
- **P11 `keeper-enterprise.v1` offline foundation:** schema, typed model load, dependency graph, field-level diff, and plan ordering now cover nodes, users, roles, teams, enforcements, and aliases. Online validate/apply remain future gaps until Commander enterprise contracts are live-proven.
- **W6a `keeper-ksm.v1` offline foundation:** schema, typed model load, dependency graph, and field-level diff now cover apps, tokens, record shares, and config outputs. Plan/apply remain preview-gated until KSM provider contracts are live-proven.
- **W14 `keeper-integrations-identity.v1` offline foundation:** schema, typed model load, and field-level diff now cover domains, SCIM provisioning, SSO providers, and outbound email. `dsk validate` is schema-only; plan/apply intentionally exit capability until Commander write/readback contracts are proven.
- **Three v1.1 offline quality gaps closed:** adoption smoke against unmanaged records, field-drift->UPDATE smoke, two-writer ownership-marker race smoke.
- **One v2 deferral:** breaking removal of `keeper_sdk`; `declarative_sdk_k` forward-compatible shim has landed.
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
| 3 | `keepercommander>=17.2.16,<18` pin | SHIPPED | `pyproject.toml`, `.commander-pin` |
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
| 6 | Adoption / field-drift / two-writer smokes | SHIPPED v1.1 (offline) | `tests/test_adoption_smoke.py`, `tests/test_vault_update_smoke.py`, `tests/test_two_writer.py` |

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
| `pamRemoteBrowser` RBI buckets | mixed | DAG → manifest merge shipped | green for supported rows | ✅ | ✅ E2E smoke rc=0 (2026-04-28). URL and typed boolean rows are supported / import-supported per `docs/COMMANDER.md`; list/audio/upstream-gap rows stay gated. |
| Nested `pamUser` shape (in `resources[].users[]`) | supported (shape) | shipped | green | scenario | `pamUserNested` |
| Nested `pamUser.rotation_settings` | supported (Commander 17.2.16+) | shipped | green | supported | GH #35 added `pam rotation list --record-uid --format json`; SDK discover readback hydrates the nested slice. |
| Top-level `users[].rotation_settings` | preview-gated | guarded | – | – | gate-lift rule: stays blocked even after nested clears |
| `default_rotation_schedule` | preview-gated | guarded | – | – | needs separate setter/readback proof |
| `jit_settings` | upstream-gap | guarded | – | – | `docs/ISSUE_6_JIT_SUPPORT_BOUNDARY.md` |
| Standalone top-level `pamUser` | preview-gated → v1.1 | guarded | – | – | `V1_GA_CHECKLIST.md` § 6 |
| Gateway `mode: create` | preview-gated / design-only | guarded | – | – | `docs/ISSUE_7_GATEWAY_CREATE_PROJECTS_DESIGN.md` |
| Top-level `projects[]` | preview-gated / design-only | guarded | – | – | same |
| KSM application provisioning (`dsk bootstrap-ksm`) | supported | shipped | live-green (bootstrap+login) | low | 2026-04-28: `tests/live/test_ksm_bootstrap_smoke.py` with `KEEPER_LIVE_TENANT=1` + KSM config — see `LIVE_TEST_RUNBOOK`. Also `docs/KSM_BOOTSTRAP.md` + 89 unit tests. Full PAM apply+KSM remains via committed smoke, not this pytest alone. |
| `KsmLoginHelper` (Commander credentials read from KSM) | supported | shipped | live: exercised on bootstrap+login path per same pytest | low | `keeper_sdk/auth/helper.py` + 175+ unit tests; `docs/KSM_INTEGRATION.md`. |
| `keeper-vault.v1` L1 (login CRUD) | supported | shipped | green | green | 2026-04-28 `vaultOneLogin` smoke passed create -> verify -> destroy; scalar field diff + apply converges. |
| `keeper-enterprise.v1` offline schema/graph/diff | supported offline | schema/model/graph/diff only | offline-green | – | P11 covers nodes, users, roles, teams, enforcements, aliases. Online validate/apply are future/upstream-gap. |
| `keeper-integrations-identity.v1` offline schema/model/diff | supported offline | schema/model/diff only | offline-green | – | W14 covers domains, SCIM provisioning, SSO providers, and outbound email. Plan/apply remain upstream-gap because no safe Commander write/readback API is confirmed. |
| KSM inter-agent bus (`secrets/bus.py`) | preview-gated (offline mock) | shipped for KSM custom-field JSON envelopes + CAS/version checks + channel message lists | offline mock | ❌ | `tests/test_ksm_bus_impl.py`; live write/readback and concurrent-writer proof still required before support lift. |
| MSP discover / validate (`msp-environment.v1`) | supported | shipped | green | green | Commander MSP `validate --online` / discover is supported for MSP admin sessions; Commander import/apply remain unsupported. |

DA Definition-of-Done compliance:
- ✅ GitHub install path works (git URL + release wheel/sdist).
- ✅ Full local checks + GitHub CI green on `main`.
- ✅ All modeled keys classify into one bucket.
- ✅ No preview-gated key silently applies or silently drops (`_detect_unsupported_capabilities` + plan CONFLICT rows; C3 + D-4 + H6).
- ⚠️ Live smoke matrix green for **all** supported mutating surfaces — yes for machine/db/dir and bucketed P3 RBI rows. Nested rotation is supported for `resources[].users[]` on Commander 17.2.16+; top-level/resource rotation remains blocked.
- ✅ Unsupported capabilities fail with clear `next_action`.
- ✅ Docs + scaffold match current behaviour.
- ✅ GitHub issue state matches behaviour.

---

## v1.1 Quality-Gap Refresh

Rows added for the v1.1 items that landed after the last reconciliation pass:

| Item | Status | Evidence in tree | Notes |
|---|---|---|---|
| Adoption lifecycle smoke (`dsk import` offline) | SHIPPED v1.1 (offline) | `tests/test_adoption_smoke.py` | Covers unmanaged-record adoption plan/apply lifecycle and ownership-marker convergence without live tenant access. |
| Field-drift UPDATE vault smoke | SHIPPED v1.1 (offline) | `tests/test_vault_update_smoke.py` | Covers scalar `login` field change -> plan UPDATE -> apply -> clean re-plan. |
| Two-writer ownership-marker coverage | SHIPPED v1.1 (offline) | `tests/test_two_writer.py` | Covers same resource with different manager -> CONFLICT, same manager -> noop, and post-release adopt path. |

## v1.2 / Phase 7 Entry Refresh

Rows added for the v1.2 state and first Phase 7 landing slice:

| Item | Status | Evidence in tree | Notes |
|---|---|---|---|
| Shared-folder validate | PHASE 7 STARTED (offline) | `tests/test_vault_shared_folder.py` | Validate/reference coverage only; no Commander write modeling or supported create/update claim yet. |
| KSM app `reference_existing` | PHASE 7 STARTED (offline) | `tests/test_ksm_app_reference.py` | Gateway read path proven for existing app references; create model remains next work. |
| KSM app create tests | PHASE 7 STARTED (offline) | `tests/test_ksm_app_create.py` | Bootstrap/create sequence covered offline; live create -> bind/share -> clean re-plan -> cleanup still required before support. |
| `keeper://` redaction pattern | SHIPPED v1.2 (offline) | `keeper_sdk/core/redact.py`, `tests/test_redact.py`, `tests/test_report_commands.py` | `keeper://...` paths are masked like KSM URLs so report notes and logs do not leak record paths. |
| Teams/roles offline validate | PHASE 7 STARTED (offline) | `tests/test_teams_roles_validate.py` | Read-only validation coverage; write support stays preview-gated. |
| `keeper-enterprise.v1` offline foundation | SHIPPED P11 (offline) | `keeper_sdk/core/schemas/enterprise/enterprise.v1.schema.json`, `keeper_sdk/core/models_enterprise.py`, `keeper_sdk/core/enterprise_graph.py`, `keeper_sdk/core/enterprise_diff.py`, `tests/test_enterprise_schema.py` | Schema + typed load + graph + field-level diff + plan ordering are supported offline; Commander online/apply remain future/upstream-gap. |
| `keeper-ksm.v1` offline foundation | SHIPPED W6a (offline) | `keeper_sdk/core/schemas/ksm/ksm.v1.schema.json`, `keeper_sdk/core/models_ksm.py`, `keeper_sdk/core/ksm_graph.py`, `keeper_sdk/core/ksm_diff.py`, `tests/test_ksm_schema.py` | Schema + typed load + graph + field-level diff are supported offline for apps, tokens, record shares, and config outputs; plan/apply remain preview-gated until provider proof lands. |
| `keeper-integrations-identity.v1` offline foundation | SHIPPED W14 (offline) | `keeper_sdk/core/schemas/integrations/identity.v1.schema.json`, `keeper_sdk/core/models_integrations_identity.py`, `keeper_sdk/core/integrations_identity_diff.py`, `tests/test_integrations_identity.py` | Schema + typed load + field-level diff are supported offline. Commander online/apply remain upstream-gap until safe write/readback contracts land. |
| Report commands offline + live | MIXED v1.2 | `tests/test_report_commands.py`, `docs/SDK_DA_COMPLETION_PLAN.md` Phase 7 | Offline compliance/security-audit sanitization covered; password-report live proof accepted; compliance/security-audit live proof remains pending. |
| Example manifests | SHIPPED v1.2 (offline) | `examples/vault/login-record.yaml`, `examples/vault/shared-folder.yaml`, `examples/msp/02-with-modules.yaml` | Adds minimal vault login, shared-folder placeholder, and MSP modules/addons examples to the validate-clean corpus. |
| `declarative_sdk_k` compatibility shim | SHIPPED v1.2/P22 | `declarative_sdk_k/__init__.py`, `tests/test_compat_shim.py`, `pyproject.toml` | New package name forwards to `keeper_sdk`; breaking removal of `keeper_sdk` remains v2.0. |
| Renderer snapshot coverage | SHIPPED v1.2 (offline) | `tests/test_renderer_snapshots.py`, `tests/fixtures/renderer_snapshots/` | Six layout snapshots lock CLI table shape for current renderers. |
| Perf memory assertion | SHIPPED v1.2 (offline) | `tests/test_perf.py` | Local gate asserts peak RSS stays under **192 MiB** for the covered workload. |
| P25 shared-folder MockProvider apply | SHIPPED v1.3.0 (offline) | `tests/test_shared_folder_apply.py`, `tests/test_cli_sharing_dispatch.py`, `tests/test_sharing_mock_provider.py`, `tests/test_sharing_mock_provider_siblings.py` | Mock apply covers create/update/noop/delete guardrails and `keeper-vault-sharing.v1` apply -> clean mock-plan convergence; Commander live support remains preview-gated until write/readback proof. |
| P26 v1.3.0 baseline | SHIPPED release baseline | `pyproject.toml`, `CHANGELOG.md` | Package metadata is on `1.3.0`; the `declarative_sdk_k` shim remains the v1.x bridge and breaking `keeper_sdk` removal waits for v2.0.0. |
| P27 blockers table + v1.3 roadmap | SHIPPED docs/index | `docs/DSK_NEXT_WORK.md` | The queue now records blockers and v1.3 roadmap items for shared-folder write support, KSM app create proof, module rename timing, and teams/roles live validate. |
| P30 shared-folder Commander create/update | SHIPPED v1.3.0 (offline) | `keeper_sdk/providers/commander_cli.py`, `tests/test_shared_folder_commander.py` | Commander provider now wires shared-folder create/update and membership grant paths with delete guardrails; full support lift still needs broader permission diff/readback proof. |
| P10 keeper-vault-sharing compatibility API | SHIPPED offline / LIVE-PENDING | `keeper_sdk/core/models_vault_sharing.py`, `keeper_sdk/core/vault_sharing_plan.py`, `tests/test_vault_sharing_schema.py`, `tests/live/test_vault_sharing_live.py` | Adds the P10-named schema/model/plan facade over the existing `keeper-vault-sharing.v1` implementation and mock lifecycle proof. The offline worker did not run or claim live second-account proof; full lifecycle support remains gated until a sanitized live transcript is captured by a credentialed harness. |
| P31 KSM inter-agent bus stub | SHIPPED, superseded by P13 preview | `keeper_sdk/secrets/bus.py`, `tests/test_ksm_bus_stub.py`, `docs/KSM_INTEGRATION.md` | Original sealed import surface remains covered for unconfigured/legacy call paths; P13 replaces configured bus use with offline-mocked CAS + publish/subscribe implementation. |
| P13 KSM inter-agent bus CAS + pub/sub | PREVIEW-GATED (offline) | `keeper_sdk/secrets/bus.py`, `tests/test_ksm_bus_impl.py`, `docs/KSM_INTEGRATION.md` | Custom text fields now carry JSON value/version envelopes; `KsmBus` supports publish/get/delete/subscribe and `BusClient` supports ordered channel send/receive/ack/gc. Live proof remains required for support lift. |

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
| Phase 2.1 (nested rotation) full close | NOT dropped — UNBLOCKED | Commander GH #35 is resolved in 17.2.16; SDK readback wiring is offline-tested, with parent live smoke still needed for final proof capture. |
| Phase 3 (RBI) full close | NOT dropped — DOC-READY | Live smoke + COMMANDER P3.1 + DA Phase 3 evidence is on `main`; maintainer issue close/update remains. |
| Adoption smoke / field-drift smoke / two-writer smoke | SHIPPED v1.1 (offline) | See `v1.1 Quality-Gap Refresh` above. |
| Module rename `keeper_sdk` → `declarative_sdk_k` | PARTLY SHIPPED / DEFERRED v2.0 | Compatibility shim landed; breaking removal of `keeper_sdk` remains a v2.0 action. |
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
5. Post-import RBI tuning — bucketed in `docs/COMMANDER.md`; only lift additional dirty/list/audio rows after focused readback proof.
6. Nested `pamUser` rotation — supported for `resources[].users[]` on Commander 17.2.16+; keep top-level/resource rotation blocked until a separate writer/readback proof exists.
7. ~~Signed `v1.0.0` tag~~ — RESOLVED 2026-04-26: annotated tag only by policy (GitHub-only repo). Sigstore/cosign of `dist/*` is the cheap upgrade path if supply-chain requirements ever appear.

---

## How to use this file (for agents)

0. For an **ordered product queue** (P3, P2.1, KSM, live vs local gates), see
   [`docs/DSK_NEXT_WORK.md`](./docs/DSK_NEXT_WORK.md) — it summarizes this file +
   completion plans; it is not a second contract.
1. Read this file to know what's open vs shipped vs deferred — **before** proposing new features.
2. Cross-link from PR descriptions when closing a row.
3. When closing a row, update **both** this file AND the source-of-truth (`V1_GA_CHECKLIST.md` or `docs/SDK_DA_COMPLETION_PLAN.md`) — never just this one.
4. When a new capability lands, add it here under its phase + classify it (`supported` / `preview-gated` / `upstream-gap`). Silent additions are forbidden.
5. Per-folder context lives in `<dir>/SCAFFOLD.md` (see refreshed root `SCAFFOLD.md` table).
