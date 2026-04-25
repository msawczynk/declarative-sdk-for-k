# `scripts/smoke/` — live-smoke harness

End-to-end create → verify → clean re-plan → destroy against a real Keeper
tenant. The only sanctioned path for live mutation. No ad-hoc CLI.

## Files

| File | LOC | Role |
|---|---:|---|
| `__init__.py` | 1 | Package marker. |
| `identity.py` | 529 | Tenant identity helpers — login bootstrap, KSM config probe, gateway/config resolution. |
| `sandbox.py` | 381 | Ephemeral tenant scaffold — `PAM Environments / customer-prod / Resources + Users`. Cleanup contract honours `SMOKE_NO_CLEANUP=1`. |
| `scenarios.py` | 349 | Registered `ScenarioSpec`s. Every scenario provides `name`, `resource_type`, `build_resources(uid_ref, title_prefix)`, `verify(records)`. Runner is invariant; only the spec changes. |
| `smoke.py` | 753 | End-to-end runner CLI. `--scenario`, `--login-helper`, `--keep`, `--dry-run`. Exits non-zero on any verifier failure; `SMOKE PASSED` on green. |
| `README.md` | – | How to run smoke + matrix; lab prerequisites. |
| `.commander-config-testuser2.json` | – | Local helper config fixture (gitignored secrets via `.gitignore`). |
| `.gitignore` | – | Keeps local smoke secrets/config out of git. |

## Registered scenarios (see `scenarios.py`)

| Name | Resource type | Status | Notes |
|---|---|---|---|
| `pamMachine` | `pamMachine` | live-verified | Reference scenario (W-series live proof, 2026-04-24/25). |
| `pamDatabase` | `pamDatabase` | scenario shipped + offline-tested | Live cmd: `--scenario pamDatabase`. |
| `pamDirectory` | `pamDirectory` | scenario shipped + offline-tested | Live cmd: `--scenario pamDirectory`. |
| `pamRemoteBrowser` | `pamRemoteBrowser` | preview-gated (P3) | Discover passes manifest source for DAG → `pam_settings.options` merge; clean re-plan parent-verified gate. |
| `pamUserNested` | `pamMachine` w/ nested `users[]` | shipped offline | Proves nested-user shape through schema/model/planner/normalize. |
| `pamUserNestedRotation` | nested `pamUser` w/ `rotation_settings` | preview (P2.1) | Apply lands; clean re-plan = open gate. |

## Where to land new work

| Change | File | Sibling to copy |
|---|---|---|
| New scenario (resource type) | `scenarios.py` (new `ScenarioSpec`) + `tests/test_smoke_scenarios.py` (offline shape check) | `pamDirectory` scenario in both files |
| New invariant verifier | `scenarios.py` (per-spec `verify`) | pamDatabase `database_type` check |
| New tenant-identity probe | `identity.py` | gateway resolution helper |
| New sandbox folder | `sandbox.py` | resources/users folder helpers |
| New runner CLI flag | `smoke.py` + `tests/test_smoke_args.py` | `--keep` |

## Hard rules

- **Live mutation only via this harness.** Never script ad-hoc `keeper` mutations from agents.
- **No secrets in stdout/stderr/log artifacts.** Honour redaction patterns; `SMOKE_NO_CLEANUP=1` for failure-case inspection only.
- **Cleanup is destroy-by-marker.** Never delete records the SDK doesn't own.
- **One scenario per `--scenario` invocation.** Matrix runs use `scripts/agent/run_smoke_matrix.sh`.
- Login helper defaults to `deploy_watcher` for matrix, `env` for the GA login proof. Override via `--login-helper`.

## Reconciliation vs design

| Requirement | Status | Evidence |
|---|---|---|
| `pamMachine` create → verify → destroy | shipped + live-green | `V1_GA_CHECKLIST.md` § 6, `AUDIT.md` 2026-04-24 |
| `pamDatabase` / `pamDirectory` / `pamRemoteBrowser` cycles registered | shipped | `scenarios.py`, `tests/test_smoke_scenarios.py` |
| Nested `pamUser` shape covered offline | shipped | `pamUserNested` scenario |
| Nested-`pamUser` rotation clean re-plan | open (SDK_DA P2.1) | apply OK; re-plan still drifts pre-fix |
| `pamRemoteBrowser` clean re-plan | open (SDK_DA P3) | DAG merge shipped; tenant verification pending |
| Adoption / field-drift / two-writer smokes | DEFERRED v1.1 | `V1_GA_CHECKLIST.md` § 6 last 3 rows |
