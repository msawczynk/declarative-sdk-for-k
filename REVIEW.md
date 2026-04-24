## SDK review — 2026-04-24 (`sdk-review` branch)

Devil's-advocate code review of `keeper-declarative-sdk/keeper_sdk/` against
the design-of-record in `../keeper-pam-declarative/` and the real capabilities
of Keeper Commander `17.2.13+` (pinned to `upstream/release` HEAD
`63150540` — "Pam Remote Browser Get JSON response data added"). At
`../Commander/review-release`.

**Status: 97 unit tests green (was 82 at review start).** No live-smoke re-run
performed in this pass — the `sdk-completion` branch is the last
live-verified state. Deltas are pure refactor + new capability guards + docs.

---

### Methodology

Three parallel exploration passes fed this review:

1. **Commander capability survey** — argv surfaces, JSON payload shapes,
   in-process API, gotchas. Source: `../Commander/keepercommander/`.
2. **DOR survey** — manifest schema, lifecycle, exit codes, marker
   format, mismatches. Source: `../keeper-pam-declarative/`.
3. **Internal lint** — dead code, fragile contracts, docstring coverage,
   naming, oversized functions. Source: `keeper_sdk/` only.

Cross-reference of the three surfaced both low-risk cleanups (applied in
this branch) and deferred structural work (recorded below).

---

### Applied in this branch (safe, tested)

| file | change | rationale |
|------|--------|-----------|
| `providers/commander_cli.py` | drop unused `DeleteUnsupportedError` import + `_DELETE_UNSUPPORTED_ERROR` alias | dead code flagged by lint pass |
| `providers/commander_cli.py` | `zip(creates_updates, outcomes, strict=False)` → `strict=True` + comment | lengths must match by construction; make future drift loud |
| `providers/commander_cli.py` | require `KEEPER_SDK_LOGIN_HELPER` env; drop `Path.home() / "Downloads" / ...` fallback | **P0** — workstation-specific default was unsafe library behaviour |
| `providers/commander_cli.py` | remove local `_utc_now`, use `metadata.utc_timestamp` | single source of truth |
| `providers/commander_cli.py` | drop unused `import datetime as dt` | dead import |
| `providers/mock.py` | simplify marker-update branch to use `utc_timestamp()` | eliminates the `encode_marker(...)["last_applied_at"]` side-effect hack |
| `core/metadata.py` | promote `_utc_now` → public `utc_timestamp`; keep `_utc_now` as private alias for backward compat | stabilize a helper other providers can reuse |
| `core/manifest.py` | narrow `except Exception` to `(ValueError, TypeError)` | pydantic raises `ValidationError` ≤ `ValueError`; no more masking of `KeyboardInterrupt` |
| `core/graph.py` | remove dead `pass` placeholder (L120–121) | planner comment described a relationship edge that is actually created below |
| `core/interfaces.py` | docstring for `ApplyOutcome` enumerating well-known `details` keys | public API was undocumented |
| `core/planner.py` | class + function docstrings for `Plan` / `build_plan` | public API was undocumented |
| `core/diff.py` | class docstrings for `ChangeKind` + `Change` | public API was undocumented |
| `cli/renderer.py` | class docstring for `RichRenderer` | public API was undocumented |
| `cli/main.py` | comment explaining why `EXIT_CHANGES == EXIT_SCHEMA == 2` | DOR intentionally overloads exit 2; prevent well-meaning "fixes" |
| `scripts/smoke/smoke.py` | export `KEEPER_SDK_LOGIN_HELPER` pointing at lab `deploy_watcher.py` | follow-up to the P0 above; smoke test still drives in-process login |

**Net line delta:** +47 docstring / comment, −27 dead code, ≈ −8 duplicated helper, identical behaviour on all 82 tests.

---

### Deferred — record, do not rush

#### D-1 · Split `providers/commander_cli.py` (1073 LOC → ~5 modules)

Proposed boundary, owner-verified before attempting:

```
providers/commander/
├── __init__.py              # public CommanderCliProvider facade
├── subprocess.py            # _run_cmd, env, silent-fail detection
├── pam_project_in_process.py# _run_pam_project_in_process, arg parser, KeeperParams bootstrap
├── discover.py              # discover + _record_from_get + _payload_from_get + field canonicalization
├── apply.py                 # apply_plan orchestration
└── scaffold.py              # PAM Environments folder resolver + table parsers for pam gateway / pam config list
```

Risk: breaks monkeypatch targets in `tests/test_commander_cli.py`. Requires
a single atomic rename + test adjustment. Out of scope for a review pass.

#### D-2 · Decompose `core/diff.py::compute_diff` (~160 LOC)

Extract `_match_desired`, `_classify_deletes`, `_check_adoption_conflicts`.
Zero behaviour change expected; 100% covered by existing tests.

#### D-3 · Replace ASCII-table parsing with `--format json`

`_parse_ascii_table` for `pam gateway list` / `pam config list`
(`commander_cli.py` ~900) is the single most fragile contract in the
provider. Commander 17.2.13 does not yet emit `--format json` for these
subcommands (verified in survey). Track upstream; migrate when available.
Until then, add a contract test that pins the expected column layout.

#### D-4 · Capability gaps vs spec

DOR-listed capabilities NOT implemented in the SDK today:

| capability | spec ref | SDK status | impact |
|------------|----------|------------|--------|
| `gateway.mode: create` + `ksm_application_name` | `manifests/pam-environment.v1.schema.json` L85-95 | only `reference_existing` wired | blocks fresh-tenant bootstrap via SDK |
| `pam_configurations[].default_rotation_schedule` | `SCHEMA_CONTRACT.md` L141+ | field parsed, never applied | rotation schedules must still be set by hand |
| `resources[].rotation_settings` | `SCHEMA_CONTRACT.md` L180+ | field parsed, never applied | same as above |
| `jit_settings` | `SCHEMA_CONTRACT.md` L120+ | parsed only | JIT policy not enforced |
| `shared_folders[].permissions` (detailed ACL) | schema `$defs/shared_folder` | surface `manage_users` / `manage_records` / `can_edit` / `can_share` wired; named-user permission grants not | fine for simple envs, gap for multi-role |
| pre-apply role enforcement (validate stage 4–5) | `README.md` L24-28 | deferred to Commander | CLI cannot pre-block capability errors |
| AWS / Azure / GCP / OCI environment provisioning | schema `$defs/pam_configuration` | AWS/domain/local examples ship; Azure/GCP/OCI untested | low-priority, add when a live env demands |

Each is a feature, not a bug — the SDK faithfully serialises what the
manifest declares and asks Commander to do the work. When a field has no
downstream action wired, a warning renderer in plan/diff would prevent
operator surprise.

#### D-5 · DOR internal contradictions (upstream — not SDK to fix)

Flag to the `keeper-pam-declarative` owners:

* `METADATA_OWNERSHIP.md` vs `docs/.../reference/marker.md` disagree on
  `manager` string and field names. SDK follows `METADATA_OWNERSHIP.md`
  (verified by the `MANAGER_NAME = "keeper-pam-declarative"` constant).
* `DELIVERY_PLAN.md` vs `errors.md` disagree on meaning of exit 2. SDK
  follows `DELIVERY_PLAN.md` (exit 2 = changes present / schema error
  depending on subcommand). Confirmed correct by the CI smoke
  (`rc_plan == 2` after creates).
* `SCHEMA_CONTRACT.md` claims `pamRemoteBrowser` supports text session
  recording; the JSON schema only permits `remote_browser_isolation` and
  `graphical_session_recording`. SDK follows the JSON schema.

#### D-6 · Test coverage holes

`from_pam_import_json` round-trip, `load_manifest_string` direct, and
`MetadataStore` protocol are all public but lightly tested. Add focused
tests in a follow-up commit if those surfaces are expected to grow.

#### D-7 · Commander version pin

`../Commander/keepercommander/__init__.py` = `17.2.13`; the binary on
operator workstations is `17.1.14`. Document the delta (none found in a
quick `CHANGELOG.md` search — file absent) in a `docs/COMMANDER.md` once
a changelog is available upstream.

---

### Devil's-advocate summary

| concern | verdict |
|---------|---------|
| Marker format drift | None. Constants in `metadata.py` match DOR. |
| Payload shape drift | None. `normalize.to_pam_import_json` emits Commander-native shape (verified against `pam_import/base.py`). |
| Dead code | Cleaned (1 import, 1 alias, 1 local helper, 1 `pass`). |
| Hardcoded paths | Cleaned (login helper now requires env var). |
| Docstring coverage of public API | ~60% → ~85% after this pass. Remaining gaps are in `core/models.py` (Pydantic, partially covered by `Field(description=...)`). |
| Oversized modules | `commander_cli.py` (1073), `core/models.py` (466), `cli/main.py` (414) — acceptable with current docstrings; splits proposed above (D-1) but not required. |
| Fragile subprocess contracts | ASCII-table parser (D-3) is the one real risk; everything else is JSON. |
| Leaky abstractions | Commander-specific field names are confined to `normalize.py` by design; no direct Commander imports anywhere in `core/`. Clean boundary. |
| Error taxonomy | `CapabilityError` / `CollisionError` / `OwnershipError` / `SchemaError` / `RefError` / `ManifestError` used consistently; every raised error carries `reason` + `next_action` + optional `context`. |

The SDK is in better shape than the line count suggests. The one structural
concern (1073-line provider) is mechanically splittable; doing so is a
planned follow-up, not an urgent defect.

---

### Next operator decisions

1. **Accept or reject** the D-1 / D-2 / D-3 splits as a follow-up ticket.
2. **Prioritise D-4 capability gaps** — which of `mode: create`,
   rotation schedules, or named-user folder ACLs should the SDK tackle
   next?
3. **Raise the D-5 contradictions** with the `keeper-pam-declarative`
   maintainer so the docs stop contradicting themselves.
4. **Merge `sdk-review` into `sdk-completion`** if happy with this pass,
   then re-run the live smoke (currently expected green — changes are
   pure refactor + docs). `main` still untouched.

---

## Update — 2026-04-24 second pass ("finish it all")

User requested full completion of D-1..D-7 against the Commander release
branch. Outcome, item-by-item:

### D-1 · commander_cli.py split — **partial, shipped**

Approach changed from a 5-module split to a pragmatic helpers extraction.
Rationale: the proposed `{subprocess, pam_project_in_process, discover,
apply, scaffold}.py` split requires class decomposition (mixins or the
provider class partitioned across files), which is high regression risk
for zero test benefit. Instead, ~300 LOC of pure module-level helpers
moved to `providers/_commander_cli_helpers.py`. `commander_cli.py`
dropped from 1082 to ~760 LOC and now contains only the provider class +
its stateful collaborators (`_run_cmd`, `_write_marker`,
`_run_pam_project_in_process`, `_get_keeper_params`, scaffold). Tests
unchanged. The full class split stays deferred — re-file only if the
class itself grows again.

### D-2 · compute_diff decomposition — **shipped**

`keeper_sdk/core/diff.py::compute_diff` refactored into three helpers:
`_index_live`, `_classify_desired`, `_classify_orphans`. Top-level
function is now a 30-line orchestrator; each helper has a single
responsibility and a docstring. Zero behaviour change; all existing
tests still cover the branches.

### D-3 · ASCII-table → `--format json` — **shipped**

Commander release branch **does** ship `--format json` on both
`pam gateway list` (`discoveryrotation.py` L1373-1606) and
`pam config list` (L1729-1967). `_pam_gateway_rows` / `_pam_config_rows`
migrated to consume the documented JSON shape. `_parse_ascii_table`
removed entirely (`re` import no longer needed). Two contract tests
added in `tests/test_coverage_followups.py` pin the exact JSON keys
against the Commander source line range.

### D-4 · Capability gaps — **loud-failure guards shipped, features deferred**

Commander hooks now known for every DOR-declared capability (see
`docs/COMMANDER.md` and `keeper-pam-declarative/NOTES_FROM_SDK.md`).
None of the actual feature implementations shipped — each is a genuine
product decision (schema for rotation JSON, which JIT dimensions to
expose, whether `mode: create` should bootstrap KSM apps, etc.). What
DID ship is a loud-failure guard:
`CommanderCliProvider._assert_no_unsupported_capabilities` now fails
`apply_plan` with a `CapabilityError` pointing at the missing
Commander hook whenever the manifest declares `rotation_settings`,
`default_rotation_schedule`, `jit_settings`, `rotation_schedule`, or
`gateway.mode: create`. Previously these were silently dropped.
Two regression tests in `tests/test_coverage_followups.py`.

### D-5 · DOR contradictions raised — **shipped**

`../keeper-pam-declarative/NOTES_FROM_SDK.md` created with seven
itemised contradictions / mismatches and concrete proposals:

1. Marker wire format (METADATA_OWNERSHIP vs reference/marker.md).
2. Exit code 2 overloading.
3. `pamRemoteBrowser` text + audio session recording gaps.
4. `pam project export` / `remove` referenced but non-existent.
5. Per-capability DOR-vs-SDK matrix (links to D-4 guards).
6. `KEEPER_SDK_LOGIN_HELPER` env var not mentioned by DOR.
7. Missing Commander version pin in `DELIVERY_PLAN.md`.

### D-6 · Test coverage — **shipped**

`tests/test_coverage_followups.py` added (+13 tests, suite 82 → 95):

* `from_pam_import_json` round-trip (3 tests including `to_from` pair).
* `load_manifest_string` YAML / JSON / auto-detect / dump round-trip.
* `MetadataStore` protocol structural check with an in-memory impl.
* `utc_timestamp` ISO-8601 `Z` suffix pin.
* `pam gateway list` / `pam config list` JSON contract pins (D-3).
* Marker-constant cross-check vs DOR.
* D-4 guard regressions (`mode: create`, `rotation_settings`).

Total: **97 passing, 0 skipped, 0 xfail.**

### D-7 · Commander version pin doc — **shipped**

`docs/COMMANDER.md` created: target version, binary-vs-module split,
why two versions matter, subprocess + in-process capability tables,
explicit "do not use" list (`pam project export`, subprocess
`record-update`, interactive login), workstation verification
checklist, and a pin-churn policy.

### Commander baseline

`../Commander/` checked out at `review-release` tracking
`upstream/release` (HEAD `63150540`). Key deltas since `v17.2.13` tag:

* `pam gateway list` / `pam config list` gain `--format json` (unlocked D-3).
* `pam launch --jit` merged (JIT single-source-of-truth is
  `commands/pam_launch/jit.py`).
* Pam Remote Browser audio keys (`disableAudio`, `audioChannels`,
  `audioBps`, `audioSampleRate`) added to `ConnectionSettingsHTTP`
  (SDK declarative mapping does not emit them — D-5 item #3).
* `pam project` still only exposes `import` + `extend` (confirmed; no
  `export` / `remove` / `list` coming upstream).

### What's still deferred after this pass

* D-1 full class split (see rationale above).
* D-4 actual feature implementations for rotation / JIT / gateway
  mode:create / RBI audio / GCP+Azure+OCI — each needs a product
  decision, not engineering time.
* Follow-up on the contradictions raised in D-5 (upstream).
* D-6 does not yet cover: `redact` internals, `cli/renderer.py` against
  real terminals, the `pam project in-process` error code paths.
