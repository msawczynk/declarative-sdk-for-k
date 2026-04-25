# SDK Live Smoke

This smoke is an autonomous, no-human-input harness for proving the SDK against a live Keeper tenant through Commander CLI 17.x, while honoring the current "no DAG writes" moratorium by routing all tenant mutations through Commander rather than direct `keeper_dag` writes. Both the `deploy_watcher` helper path and the public `EnvLoginHelper` path are wired into the same plan -> apply -> verify -> destroy harness; Issue #3 is live-proven for the full `pamMachine` cycle.

The `pamRemoteBrowser` and `pamUserNestedRotation` scenarios are proof harnesses, not support claims for Issues #5 and #4. A 2026-04-25 `pamRemoteBrowser` live run created records and cleanup passed, but verification failed because Commander `pam rbi edit --remote-browser-isolation` writes DAG `allowedSettings.connections`, which current `discover()` does not read back as manifest-shaped `pam_settings.options.remote_browser_isolation`. Nested rotation now reaches apply and marker verification after `pam rotation edit`, but the follow-up plan still reports updates for the nested user and parent machine; keep the preview/experimental gates until readback/drift semantics are clean. **Phase 0 / merge gates:** `docs/SDK_DA_COMPLETION_PLAN.md` § Phase 0 and `scripts/agent/phase0_gates.sh` — do not lift preview gates without parent-reviewed live proof per that plan.

## Prerequisites

- Keeper Commander >= 17.2.13 on PATH (`keeper --version`)
- `pip` packages installed: `keepercommander`, `pyotp`, `keeper_secrets_manager_core`, `pyyaml`
- Admin KSM config at `../keeper-vault-rbi-pam-testenv/ksm-config.json`
- Admin commander config at `../keeper-vault-rbi-pam-testenv/commander-config.json` with a valid `device_token` (persistent login)
- Admin has already stored admin-KSM record `MyiZN4cw-wtEIpY1jHlhLw` ("Admin Creds for Lab Scripts" or similar) containing the admin login, password, and `oneTimeCode`
- Tenant contains the gateway `Lab GW Rocky` bound to PAM configuration `Lab Rocky PAM Configuration`
- `testuser2` (`msawczyn+testuser2@acme-demo.com`) exists and is active

## Files

| file | purpose | public functions |
|------|---------|------------------|
| `identity.py` | Bootstraps the live identities: admin login via KSM-backed lab helpers, plus idempotent `testuser2` TOTP provisioning and Commander config reuse. | `admin_login()`, `ensure_sdktest_identity()`, `sdktest_keeper_args()`, `main()` |
| `sandbox.py` | Ensures the reusable shared-folder sandbox and KSM app exist, are shared correctly, and can tear down only SDK-managed records. | `ensure_sandbox()`, `record_count()`, `teardown_records()`, `teardown_sandbox()`, `main()` |
| `scenarios.py` | Registry of resource shapes the smoke can exercise. Each `ScenarioSpec` supplies a manifest fragment builder and a post-apply verifier; the runner is resource-type-agnostic. | `get()`, `names()`, `all_scenarios()` |
| `smoke.py` | Orchestrates the live end-to-end smoke: pre-clean, manifest generation, validate/plan/apply, live verification, destroy, and failure cleanup. Scenario-aware via `--scenario`. | `run_smoke()`, `main()` |

## One-command run

Full matrix (all scenarios, logs under `.smoke-runs/`, gitignored):

```bash
scripts/agent/run_smoke_matrix.sh
scripts/agent/run_smoke_matrix.sh --login-helper env
```

Single scenario:

```bash
python3 scripts/smoke/smoke.py                          # pamMachine (default)
python3 scripts/smoke/smoke.py --scenario pamDatabase   # Postgres cycle
python3 scripts/smoke/smoke.py --scenario pamDirectory  # OpenLDAP cycle
python3 scripts/smoke/smoke.py --scenario pamRemoteBrowser
python3 scripts/smoke/smoke.py --scenario pamUserNested # machine + nested users[]
python3 scripts/smoke/smoke.py --login-helper env --scenario pamMachine
python3 scripts/smoke/smoke.py --login-helper env --scenario pamRemoteBrowser # Issue #5 proof; currently expected to expose RBI readback gap
DSK_PREVIEW=1 DSK_EXPERIMENTAL_ROTATION_APPLY=1 python3 scripts/smoke/smoke.py --login-helper env --scenario pamUserNestedRotation
```

Registered scenarios live in `scripts/smoke/scenarios.py`. Every scenario
is unit-tested offline (`tests/test_smoke_scenarios.py`) — schema,
typed-model, planner, and Commander JSON normalization all run without
a tenant, so scenario drift is caught before you burn a tenant
round-trip.

| scenario | status | note |
|----------|--------|------|
| `pamMachine` | supported | Default two-host Linux machine cycle. |
| `pamDatabase` | supported | Postgres cycle. |
| `pamDirectory` | supported | OpenLDAP cycle. |
| `pamRemoteBrowser` | experimental proof | Issue #5 RBI readback gap remains. |
| `pamUserNested` | supported nested shape | Machine with `resources[].users[]`; not standalone top-level user support. |
| `pamUserNestedRotation` | experimental preview | Requires `DSK_PREVIEW` plus `DSK_EXPERIMENTAL_ROTATION_APPLY`; Issue #4 drift gap remains. |

Not-supported-yet smoke coverage belongs in `docs/SDK_DA_COMPLETION_PLAN.md` § Phase 0 until it is registered in `scripts/smoke/scenarios.py` and live-proofed.

`--login-helper deploy_watcher` is the default and preserves the current
lab-helper path. `--login-helper env` unsets `KEEPER_SDK_LOGIN_HELPER`
for SDK subprocesses and instead exports `KEEPER_EMAIL`,
`KEEPER_PASSWORD`, and `KEEPER_TOTP_SECRET` so the provider falls back
to the public `EnvLoginHelper` contract. The smoke log and failure
post-mortem explicitly name which auth path ran: `deploy_watcher`
helper vs public `EnvLoginHelper` env path.

Exit codes come from `smoke.py::main()`:

| code | meaning |
|------|---------|
| `0` | Smoke passed, or `--teardown` completed successfully |
| `2` | Interrupted run, smoke/assertion failure, or SDK command failure after cleanup was attempted |
| `3` | Preflight failure before the main smoke cycle started |
| `4` | Tenant or provider constraint failure, such as a missing or invisible required gateway |

## What the smoke exercises

- Logs in as the tenant admin with `identity.admin_login()`
- Ensures the `testuser2` smoke identity exists and is usable with `identity.ensure_sdktest_identity()`
- Ensures the reusable sandbox exists with `sandbox.ensure_sandbox()`: shared folder `SDK Test (ephemeral)`, KSM app `SDK Test KSM`, gateway visibility, app binding, and share to `testuser2`
- Pre-cleans the sandbox with `sandbox.teardown_records(..., manager=MANAGER_NAME)` to remove orphaned SDK-managed records from prior runs
- Writes a scenario-specific smoke manifest and an empty destroy manifest
- Runs SDK `validate` against the generated manifest
- Runs SDK `plan` and expects exit `2` because the initial plan should contain creates
- Runs SDK `apply --auto-approve` to create the scenario records
- Discovers live state through `CommanderCliProvider.discover()` and verifies every expected SDK-managed scenario record, including nested `pamUser` records for `pamUserNested`
- Runs SDK `plan` again and expects exit `0` for a clean re-plan
- Runs SDK `plan --allow-delete` against the empty manifest and expects exit `2` because deletes should be present
- Runs SDK `apply --allow-delete --auto-approve` against the empty manifest
- Re-discovers live state and verifies no records carrying this SDK ownership marker remain

## Teardown

`python3 scripts/smoke/smoke.py --teardown` runs the same auth, identity, sandbox, and pre-clean path, then stops after deleting SDK-managed records in the sandbox shared folder. The delete guard lives in `sandbox.teardown_records()`: it lists records in the target shared folder, reads each record's `keeper_declarative_manager` marker, decodes it, and deletes only records whose decoded payload has `manager == MANAGER_NAME`.

## Troubleshooting

| symptom | next action |
|---------|-------------|
| `two_factor_code_invalid` | `identity.py` retries on the next TOTP window, once per window, up to 3 attempts; if it persists, re-run with `--force` to reprovision `testuser2` TOTP state |
| `keeper CLI not found on PATH` | Install `keepercommander` via `pip` so the `keeper` executable is available |
| `Required gateway 'Lab GW Rocky' is not visible` | The admin session cannot see the gateway; ensure the admin `commander-config.json` belongs to a user with access, then re-run |
| `Commander returned non-JSON` from `ls` on an empty folder | Already handled internally in `sandbox._loads_json()`: empty output is treated as `[]` |
| Keeper subprocess commands hang | They should not hang after `--batch-mode` plus `KEEPER_PASSWORD`; if they do, check that the `testuser2` Commander config still has a valid `device_token` and `clone_code` |
| SDK command failure | The post-mortem includes the full SDK command, exit code, stdout tail, and stderr tail so the parent/live runner can see Commander/provider details without rerunning blind |

## Non-negotiable constraints

No `keeper_dag` imports are allowed in this workflow, all tenant-side mutations must go through Commander CLI calls, the smoke must stay idempotent across reruns by reusing and pre-cleaning its sandbox, and teardown must never delete records that are not explicitly marked as SDK-managed.

## Tenant state after a passing run

- The shared folder `SDK Test (ephemeral)` remains in place for reuse
- The KSM application `SDK Test KSM` remains in place and bound to the sandbox shared folder
- The share from the sandbox shared folder to `testuser2` remains in place
- All SDK-managed records created inside the sandbox shared folder during the smoke are deleted by the destroy phase
