# `tests/` — offline coverage

All offline. No real Keeper, no real subprocess for product code. `_run_cmd` +
`shutil.which` mocked in provider tests. **Exception:** `test_daybook_harness.py`
runs `bash scripts/daybook/harness.sh` (no `~/.cursor-daybook-sync` required for
`help` / `print-env`). Live coverage lives in `scripts/smoke/`.

`pytest -q` → currently ~110+ tests green. CI matrix: 3.11 / 3.12 / 3.13.

## Files

| File | LOC | What it pins |
|---|---:|---|
| `conftest.py` | – | Shared fixtures (manifest factories, fake providers, env hygiene). |
| `test_manifest.py` | 49 | Load/dump YAML+JSON + canonicalize round-trip. |
| `test_schema.py` | 33 | Auto-discovers every `examples/invalid/*.yaml` (W9). 7 invalid fixtures + valid corpus. |
| `test_rules.py` | 104 | Semantic rules (cfg-required, RBI no JIT, rotation only on machine/db/dir). |
| `test_graph.py` | 110 | Graph build + topo + cycle detection + shared-folder/projects walk (W5). |
| `test_diff.py` | 351 | Change classification + adoption gate (W4) + collision (W7) + ignored placement metadata + nested-pamUser rotation drift anchor (P2.1). |
| `test_planner.py` | 20 | Plan summary accounting. |
| `test_normalize.py` | 84 | Manifest ↔ Commander `pam_import` shape round-trip. |
| `test_metadata.py` | 43 | Marker encode/decode + `MANAGER_NAME` cross-check vs DOR. |
| `test_redact.py` | 44 | Redaction patterns (passwords, tokens, JWTs, KSM URLs, bearer). |
| `test_renderer_snapshots.py` | 228 | RichRenderer plan/diff/outcomes byte-snapshots in `tests/fixtures/renderer_snapshots/`. |
| `test_interfaces.py` | 9 | Protocol shape conformance. |
| `test_providers.py` | 66 | Provider protocol + common-provider behaviour. |
| `test_preview_gate.py` | 202 | Preview gates unsupported rotation locations, `jit_settings`, `gateway.mode: create`, `default_rotation_schedule`, and `projects[]`; nested `resources[].users[].rotation_settings` validates without preview. |
| `test_uid_ref_gate.py` | 22 | `pam_configuration_uid_ref` cross-manifest gate (stage 3 fail). |
| `test_perf.py` | 73 | 500 `pamMachine` validate→graph→diff→plan inside 5 s budget; `resource.getrusage` mem assert. `@pytest.mark.slow`. |
| `test_cli.py` | 297 | Click commands; exit codes; `apply --dry-run == plan` byte equivalence (W3/W10). |
| `test_commander_cli.py` | 3339 | Live-provider behaviour fully under mocks. discover/apply/marker writeback/verify/delete/scaffold/JSON contracts/in-process/login bootstrap/floor gate/partial-apply outcomes. |
| `test_coverage_followups.py` | 333 | D-6 follow-ups: `from_pam_import_json` round-trip, `load_manifest_string`, `MetadataStore` protocol, `utc_timestamp` ISO-8601 Z, JSON-contract pins for `pam gateway list`/`pam config list`, marker constants, D-4 guards. |
| `test_h_series_gaps.py` | 360 | H1–H6 regression: `_run_cmd` exit, silent-fail detector, post-apply `CollisionError`, exit-4 conflict gate, marker version error, env-var/path failure modes, plan==apply CONFLICT parity (C3). |
| `test_stage_5_bindings.py` | 360 | `validate --online` stage 5 — pam_configuration presence, shared-folder reachability, KSM app binding, gateway pairing cross-check. |
| `test_smoke_args.py` | 129 | Smoke-runner CLI arg surface (offline). |
| `test_daybook_harness.py` | – | `harness.sh` help/print-env/`doctor` (ok/missing/mis-set scripts); boot + mis-set `DAYBOOK_SYNC_ROOT` stderr. Unix-only. |
| `test_smoke_scenarios.py` | 297 | Each registered scenario's manifest fragment validates + plans clean offline. |
| `test_dor_scenarios.py` | 147 | DOR `TEST_PLAN.md` scenario mapping. Includes Commander partial-apply + floor-gate (`test_apply_partial_failure_records_outcomes_then_raises`, `test_apply_rejects_keepercommander_below_minimum`). |
| `test_auth_helper.py` | 197 | `EnvLoginHelper` + Commander `LoginUi` contract. No network. |
| `test_sync_upstream.py` | 242 | `scripts/sync_upstream.py` capability-mirror generator + `--check` mode. |
| `test_rbi_readback.py` | 144 | `_record_from_get` + `_merge_rbi_dag_options_into_pam_settings` for `pamRemoteBrowser` discover (P3). |
| `test_errors.py` | 12 | `DeleteUnsupportedError` compat shim still subclass of `CapabilityError`. |
| `fixtures/examples/README.md` | – | Vendored example corpus pointer. |
| `fixtures/renderer_snapshots/*.txt` | – | Renderer byte-snapshots. |

## Where to land new work

| Change | File | Sibling to copy |
|---|---|---|
| New schema invalid fixture | `examples/invalid/<name>.yaml` (auto-picked by `test_schema.py`) | existing invalids |
| New diff/adoption case | `test_diff.py` | adoption-gate test |
| New CLI verb test | `test_cli.py` | `import` command tests |
| New provider behaviour | `test_commander_cli.py` (giant; group by topic) | nearby helper test |
| New semantic rule | `test_rules.py` | RBI-no-JIT |
| New preview-gated key | `test_preview_gate.py` | gateway/default-rotation cases |
| New live-smoke scenario shape | `test_smoke_scenarios.py` | `pamRemoteBrowser` shape test |
| New stage-5 binding | `test_stage_5_bindings.py` | gateway pairing case |
| New DOR scenario mapping | `test_dor_scenarios.py` | partial-apply row |

## Hard rules

- No real network. No real `keeper` CLI invocation.
- New tests should add ≤ 1 fixture file; prefer factories in `conftest.py`.
- Renderer snapshots: regenerate with explicit intent, never auto.
- Tests touching the live provider mock `_run_cmd` AND `shutil.which`.

## Reconciliation vs design

| DOR / V1_GA row | Status | Test |
|---|---|---|
| `apply --dry-run` byte-identical to `plan` | shipped | `test_cli.py` |
| `compute_diff(adopt=False)` default CONFLICT for unmanaged title-match | shipped | `test_diff.py` |
| Stage-5 tenant bindings | shipped | `test_stage_5_bindings.py` |
| Plan == apply == apply --dry-run capability rows (C3) | shipped | `test_h_series_gaps.py` (H6) + `test_commander_cli.py` |
| `keepercommander` floor gate | shipped | `test_commander_cli.py::test_apply_rejects_keepercommander_below_minimum` |
| Partial-apply outcomes recorded then raise | shipped | `test_commander_cli.py::test_apply_partial_failure_records_outcomes_then_raises` |
| Two-writer race (P4 acceptance) | DEFERRED v1.1 | – (open) |
| Field-drift → UPDATE smoke | DEFERRED v1.1 | – (open) |
| Adoption smoke against unmanaged records | DEFERRED v1.1 | – (open) |
