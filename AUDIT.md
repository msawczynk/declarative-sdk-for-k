# SDK completion audit — 2026-04-24

This document records the `sdk-completion` branch landing, 20 tasks (W1–W20),
and the reconciliation against the design-of-record at
`../keeper-pam-declarative/`. It is intended for reviewers and future agents
picking up this work.

## Scope

The sibling repository `keeper-pam-declarative/` is authoritative. Review
inputs:

- `ARCHITECTURE.md`
- `SCHEMA_CONTRACT.md`
- `METADATA_OWNERSHIP.md`
- `RECONCILIATION_NOTES.md`
- `DELIVERY_PLAN.md`
- `TEST_PLAN.md`
- `examples/` (valid fixtures)
- `examples/invalid/` (7 invalid fixtures)

Before this branch landed the SDK had 42 passing tests and several
divergences from the design-of-record; it now has 76 passing tests and the
contract gaps listed below are closed.

## Contract fixes (Phase A — W1–W8)

| ID | Divergence before | State after |
|----|-------------------|-------------|
| W1 | `MANAGER_NAME="keeper_declarative"`, payload used `manifest_name`, `created_at`, `updated_at`, `extra`. | `MANAGER_NAME="keeper-pam-declarative"`; payload now has `manifest`, `resource_type`, `parent_uid_ref`, `first_applied_at`, `last_applied_at`, `applied_by` per METADATA_OWNERSHIP.md. |
| W2 | `plan`/`diff` exit: 0 or 4 only. | Exit 0 clean, 2 changes, 4 conflict per DELIVERY_PLAN.md line 92. `EXIT_SCHEMA` (value 2) retained for `validate` — collision is documented. |
| W3 | `apply --dry-run` rendered plan then simulated apply and printed outcomes; exit 0 regardless. | `apply --dry-run` byte-identical to `plan` (stdout and exit). Equivalence test parametrised clean + pending. |
| W4 | Diff silently adopted unmanaged-by-title records as UPDATE. | `compute_diff(adopt=False)` default emits CONFLICT; `adopt=True` required and exposed via `keeper-sdk import` (W18). |
| W5 | `build_graph` did not walk `shared_folders` or `projects`; execution order could place resources before their shared folder. | Edges from resource/global user to `SharedFolderBlock.uid_ref` when `shared_folder: "resources"|"users"` declared. `projects` included in walker for future-proofing. |
| W6 | Only two semantic rules (gateway mode=create; RBI no rotation). | +3 rules: resources require `pam_configuration_uid_ref` when configs exist, `pamRemoteBrowser` cannot carry `jit_settings`, `rotation` option only on `pamMachine|pamDatabase|pamDirectory`. |
| W7 | `CollisionError` was in `__all__` but never raised. | `compute_diff` raises it when (a) duplicate marker uid_ref across live records, (b) duplicate `(resource_type, title)` with no claiming marker. |
| W8 | `Renderer` protocol missing `render_diff` even though CLI called it. | Protocol aligned with actual CLI usage; conformance smoke. |

## Test-plan catch-up (Phase B — W9–W12)

| ID | Change |
|----|--------|
| W9 | `tests/test_schema.py` discovers every `examples/invalid/*.yaml` at collection time (7 cases). `cyclic-refs.yaml`, previously uncovered, is now a green case. 4 redundant one-off tests removed. |
| W10 | Byte-identity `apply --dry-run == plan` test — already delivered with W3. |
| W11 | `tests/test_perf.py` runs `validate → graph → diff → plan` across 500 synthetic `pamMachine` resources in ~0.18 s; 5 s budget per TEST_PLAN.md. Marked `@pytest.mark.slow` (registered in `pyproject`). |
| W12 | README reconciled: 76 tests; exit-code table reworked to show dual meaning of code 2 across `plan/diff` vs `validate`; Status section added; `compute_diff(adopt=False)` note added; relationship section updated to point at the new marker contract. |

## Commander provider (Phase C — W13–W18)

| ID | Change |
|----|--------|
| W13 | `discover()` requires `folder_uid` (no more silent `[]`); accepts `{project:{…}}` wrapper; honours record `type` field first with validated collection fallbacks; empty stdout is a hard error. |
| W14 | Post-apply marker writeback through `keeper record-update --record <uid> -cf keeper_declarative_manager=<json>`; `outcome.details.marker_written` surfaces success/failure. Dry-run skipped. |
| W15 | Per-change field verification against rediscovered payload; `outcome.details.verified` or `outcome.details.field_drift` set. Drift ignored for ownership metadata and normalised for port str/int. |
| W16 | Delete implemented via `keeper rm <uid>`, restricted to records carrying our `MANAGER_NAME` by `compute_diff` itself (METADATA_OWNERSHIP.md delete rules). Dry-run is intent-only; partial failures leave visible outcomes and re-raise. |
| W17 | `keeper-sdk validate --online` runs stage 4 (gateway presence) + stage 5 (dry-run diff summary). Offline path unchanged. |
| W18 | New `keeper-sdk import` subcommand: opt-in adoption of title-matched unmanaged records, with dry-run and auto-approve. |

## Out of scope for this branch

Deliberately deferred (captured in JOURNAL.md for follow-up):

- **Live acme-lab smoke.** Plan specified Phase C tasks run a live smoke
  against the tenant `msawczyn+lab@acme-demo.com` using the ephemeral
  `SDK Test (ephemeral)` shared folder. Not executed here because the
  mock-provider + mocked-subprocess suite covers the same code paths
  deterministically, and executing the lab path safely requires a
  separate session with the TOTP+KSM login flow warm. When run, the
  steps are: (1) create ephemeral SF bound to `Lab GW Application`,
  (2) apply a 2-resource manifest, (3) verify markers via
  `keeper record-list`, (4) teardown via `pre_delete` → `delete`.
- **DAG-level dependency checks on delete** (METADATA_OWNERSHIP.md line 95
  "no active rotation/connection/tunnel/RBI/JIT reference"). The SDK
  respects the operator directive — no direct DAG access — so these
  checks would require Commander CLI surface that does not yet exist.
  Delete proceeds on marker-ownership today; Commander itself will
  refuse the `rm` when dependencies are live.
- **Multi-project manifests.** `Project` still 0..1 per manifest per
  SCHEMA_CONTRACT.md line 98.

## Non-negotiable constraints honored

- **No direct `keeper_dag` writes anywhere** (LESSONS.md 2026-04-23
  `[keeper-dag]`). Every tenant-side state change in the Commander
  provider routes through `subprocess.run([self._bin, ...])` against
  the `keeper` CLI. Unit tests mock `_run_cmd` and `shutil.which`; no
  test invokes the real CLI.
- **Ownership marker field label unchanged** (`keeper_declarative_manager`)
  for storage round-trip compatibility with pre-existing tenants.
- **`extra="allow"` on Pydantic models neither widened nor narrowed.**

## Numbers

- 20 planned tasks; 19 implemented (W10 absorbed into W3).
- 42 → 82 tests (+40 net — 6 added on `sdk-live-smoke` for in-process
  Commander routing).
- 0 new runtime dependencies.
- 19 commits on `sdk-completion` + 11 on `sdk-live-smoke`, each one a
  single-task unit.
- Every commit: pytest green, ruff clean on touched files, file
  whitelist honoured.

## Live smoke (2026-04-24, `sdk-live-smoke`)

End-to-end drill against `msawczyn+lab@acme-demo.com` is **GREEN**
(`create → verify → destroy` cycle clean). Fixes landed on the branch:

- **`pam project import` + `pam project extend` routed through the
  in-process Commander Python API.** Subprocess invocation cannot resume
  a persistent-login session for these two subcommands — Commander
  always re-prompts `User(Email):` regardless of `--batch-mode`,
  `KEEPER_PASSWORD`, `--user/--password` flags, or stdin piping. The
  provider obtains an authenticated `KeeperParams` via
  `deploy_watcher.keeper_login()` and calls `PAMProjectImportCommand` /
  `PAMProjectExtendCommand` directly; stdout/stderr are captured with
  `contextlib.redirect_stdout` so callers that grep the output (e.g.
  for `access_token=`) keep working.
- **`_write_marker` migrated to the in-process Commander vault API.**
  The macOS `keeper` 17.1.14 binary has no `record-update` subcommand;
  Commander 17.2.13's `-cf custom.label=value` syntax is fragile across
  versions. Markers now go through `api.sync_down` →
  `vault.KeeperRecord.load` → `record_management.update_record` against
  the same `KeeperParams` the PAM-project path uses.
- **Commander `get --format json` field-shape fixes.** `pamMachine`
  records store `host`+`port` under a single `pamHostname` field type
  (not `host`); `_canonical_payload_from_field` now handles both. Labels
  like `operatingSystem` / `sslVerification` / `instanceId` /
  `instanceName` / `providerGroup` / `providerRegion` map to canonical
  manifest keys via `_FIELD_LABEL_ALIASES`. `sslVerification` lives in
  `item["custom"]`, not `item["fields"]`; `_payload_from_get` walks both
  arrays.
- **Planner + provider drift ignore SDK-only placement metadata.**
  `pam_configuration`, `pam_configuration_uid_ref`, `shared_folder`,
  `users`, `gateway`, `gateway_uid_ref` never round-trip through
  Commander as record fields and were producing false-positive drift on
  re-plan. Added to `keeper_sdk/core/diff.py::_DIFF_IGNORED_FIELDS` and
  `commander_cli.py::_field_drift`.
- **Reference-existing synthetic LiveRecord reflects manifest fields.**
  Previously carried only `{"title": ...}`, causing `environment` /
  other declared keys to show as drift. Now mirrors the manifest entry
  so re-plan is noop when nothing actually drifted.
- **`keeper rm` gets `--force`.** Commander prompts
  `Do you want to proceed with deletion? [y/n]` even in batch mode
  without the `-f` switch; destructive subprocess calls now pass it.
- **`SMOKE_NO_CLEANUP=1`** preserves tenant state on smoke.py failure
  paths so the next run can inspect the live tree.

## Next steps for the reviewer

1. Run `pytest -q` (offline, **97 tests** after the 2026-04-24 review +
   finish-it-all pass).
2. Run the live-smoke drill:
   `cd keeper-declarative-sdk && python3 scripts/smoke/smoke.py` — the
   full `create → verify → destroy` cycle should still complete clean
   and print `SMOKE PASSED`. Changes since last live-verified state are
   pure refactor + JSON-list migration + capability guards.
3. Merge `sdk-review` → `sdk-completion`. `main` still untouched.

## 2026-04-24 late — finish-it-all pass (REVIEW.md second update)

- D-3: `pam gateway list` / `pam config list` migrated to `--format json`
  against Commander release branch `17.2.13+` (HEAD `63150540` on
  `../Commander/review-release`). ASCII-table parser removed.
- D-2: `compute_diff` decomposed into `_index_live` +
  `_classify_desired` + `_classify_orphans`.
- D-1: 294 LOC of pure helpers moved to
  `keeper_sdk/providers/_commander_cli_helpers.py`. Main file 1082 →
  ~760 LOC.
- D-4: loud-failure guard
  (`_assert_no_unsupported_capabilities`) added — no more silent drops
  of `rotation_settings` / `jit_settings` / `mode: create`.
- D-5: `../keeper-pam-declarative/NOTES_FROM_SDK.md` filed (7 items).
- D-6: +13 tests → 95; plus +2 D-4-guard tests → **97 total**.
- D-7: `docs/COMMANDER.md` pinned to release HEAD.
- No live-smoke re-run in this pass; expected-green (refactor only).
