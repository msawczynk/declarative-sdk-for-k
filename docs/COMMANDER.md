# Commander dependency pin

The SDK shells out to the **Keeper Commander** CLI (`keeper`) and imports its
Python module in-process for a handful of commands. This page documents the
exact version we target, the deltas vs older binaries operators may still
have on disk, and the subset of Commander capabilities the SDK relies on.

## Target version

| artefact | version | reference |
|----------|---------|-----------|
| Python module (`keepercommander`) | `17.2.13` tag + ~40 commits on `upstream/release` | `../Commander/keepercommander/__init__.py::__version__`; HEAD `63150540` ("Pam Remote Browser Get JSON response data added") at time of pin |
| Bundled macOS `keeper` binary at `/Applications/Keeper Commander.app/Contents/Resources/app.asar/node_modules/.../keeper` | `17.1.14` | some operator workstations still have the older binary installed via the signed DMG |
| Upstream repo | [`Keeper-Security/Commander`](https://github.com/Keeper-Security/Commander) | branch `release` is the canonical source-of-truth for this pin |

The SDK works with any `keeper` binary ≥ `17.1.14`, but **requires the Python
module at `17.2.13` or newer** for the in-process code paths (`pam project
import`/`extend`, `_write_marker`). `CommanderCliProvider.apply_plan()` reads
`importlib.metadata.version("keepercommander")` and raises `CapabilityError`
before mutating the tenant when the installed wheel is below that floor (see
`tests/test_commander_cli.py::test_apply_rejects_keepercommander_below_minimum`).
If `pip show keepercommander` reports an older version, `apply` will fail with
that gate even when the `keeper` binary is newer.

## Why two versions matter

Three concrete deltas that the SDK has to work around:

1. **`record-update`** — Commander `17.1.14` (binary) does **not** ship a
   `record-update` command. `17.2.13` adds it but the typed-field syntax
   (`-cf label=value`) is unstable across patch releases. The SDK bypasses
   the subcommand entirely: `_write_marker` calls `record_management.
   update_record` through the in-process Python API instead.
2. **`pam project import` / `pam project extend`** — subprocess invocation
   cannot resume a persistent-login session for these two verbs (they
   re-prompt for `User(Email):` mid-run). The SDK routes them through
   `PAMProjectImportCommand.execute(params, ...)` in-process.
3. **`pam gateway list` / `pam config list --format json`** — only
   available on `17.2.13+` (release branch). Older binaries fall back to
   ASCII tables, which the SDK no longer parses. If a downgrade is
   required, re-add `_parse_ascii_table` from git history
   (commit `31a8014^`).

## Capabilities the SDK uses

### Subprocess (via `keeper` binary)

| command | used for | flags |
|---------|----------|-------|
| `ls <folder_uid> --format json` | `discover` listing | `--format json` |
| `get <uid> --format json` | `discover` record fetch | `--format json` |
| `mkdir -uf <path>` | scaffolding the `PAM Environments` tree | user-folder flag |
| `mkdir -sf --manage-users --manage-records --can-edit --can-share <path>` | per-project Resources/Users shared folders | shared-folder flag |
| `secrets-manager share add --app <app> --secret <sf_uid> --editable` | bind scaffolded shared folders to the gateway's KSM app | |
| `pam gateway list --format json` | resolve `mode: reference_existing` gateway UID / KSM app UID | ships in `17.2.13+` |
| `pam config list --format json` | resolve reference-existing PAM configuration UID | ships in `17.2.13+` |
| `rm --force <uid>` | delete orphaned managed records in `apply --allow-delete` | `--force` skips the interactive confirm |

### In-process (via `keepercommander` Python module)

| class / function | used for |
|------------------|----------|
| `keepercommander.commands.pam_import.edit.PAMProjectImportCommand.execute` | create project scaffold + PAM data in one call |
| `keepercommander.commands.pam_import.extend.PAMProjectExtendCommand.execute` | add resources to an existing configuration |
| `keepercommander.api.login` (via `deploy_watcher.py` helper) | bootstrap a `KeeperParams` for the provider |
| `keepercommander.record_management.update_record` | write the `keeper_declarative_manager` custom field |
| `keepercommander.vault.KeeperRecord.load` | hydrate typed record for the marker write |
| `keepercommander.vault.TypedField.new_field` | build the custom-field entry |
| `keepercommander.api.query_enterprise` | MSP slice: refresh `params.enterprise` (including `managed_companies[]`) for `CommanderCliProvider.discover_managed_companies()` |

### MSP managed companies (`msp-environment.v1`)

The SDK **does not** shell out to `keeper msp-down` for MSP discover. The
Commander provider calls **`api.query_enterprise(params)`** in-process (same
data the `msp-info` table is built from) and maps each `managed_companies[]`
row to the manifest diff shape (`name`, `plan`, `seats`, `file_plan`, `addons`,
`mc_enterprise_id`). Operators can still run **`keeper msp-down`** manually
before `dsk` if their local `KeeperParams` cache is stale.

| Area | Commander surface | SDK status |
|------|-------------------|------------|
| Discover / `validate --online` | `api.query_enterprise` → enterprise payload | **Supported** on `commander` provider (requires MSP admin login). |
| Plan / diff (live rows) | same discover path | **Supported** when discover succeeds. |
| `apply` / `dsk import` (mutate MC or write declarative ownership marker) | `msp-add`, `msp-update`, `msp-remove`, enterprise MSP APIs | **Not implemented** in `CommanderCliProvider` — `apply_msp_plan` and MSP `import` stay `CapabilityError` until a committed marker/write contract exists (`docs/MSP_FAMILY_DESIGN.md`). |

### Post-import connection / RBI tuning field map

This is the Issue #5 / Job D field map. It maps manifest fields to Commander
import support vs. post-import edit hooks. It does **not** claim live support:
`apply_plan()` now has offline-tested wiring that imports or extends the
project, rediscovers records, resolves live Keeper UIDs, and runs mapped
`pam connection edit` / `pam rbi edit` argv via `_run_cmd()`. The committed smoke
harness and `docs/live-proof/keeper-pam-*.sanitized.json` show **pamMachine /
pamDatabase / pamDirectory / pamRemoteBrowser** E2E on the Acme-lab bar; *per
field* readback still depends on whether Commander returns the value on `get`
or only on the DAG (see P3.1 buckets in the `pamRemoteBrowser` subsection
below). Treat rows without a clean bucket as wiring-only until a focused proof
or unit test names them.

### SDK_DA §P3.1 readback buckets (design vocabulary)

Map each manifest field to one bucket (see `docs/SDK_DA_COMPLETION_PLAN.md` §P3.1):

| Bucket | Meaning |
|--------|---------|
| **import-supported** | `pam project import` / `extend` owns the value; `discover()` returns manifest-shaped fields for diff. |
| **edit-supported-clean** | Post-import `pam connection edit` / `pam rbi edit` persists it **and** `discover()` round-trips into the same manifest path used in `compute_diff` (live proof still required before any gate lift). |
| **edit-supported-dirty** | Edit persists on tenant/DAG surfaces Commander uses, but current `get`/`discover()` does **not** populate the manifest field the planner compares — clean re-plan may stay red until readback is extended (RBI isolation/recording rows below, Issue #5). |
| **upstream-gap** | No safe Commander writer in the pinned matrix, or no typed manifest path — schema may exist; apply stays preview-gated or conflicted. |

Rows in the table below mix **offline apply-wired** (argv exists) with readback
truth: treat “tuning-supported (offline apply-wired)” **without** a P3.1
bucket assignment as **at best** `edit-supported-dirty` until a proof or
`test_rbi_readback` / smoke names them.

**Issue #5 (2026-04-28):** `scripts/smoke/smoke.py --scenario pamRemoteBrowser`
on the Acme-lab bar **SMOKE PASSED** (create → clean post-apply re-plan →
destroy). Readback fixes on `main` include: (1) typed field `rbiUrl` coalesced
to manifest `url` in `discover()`; (2) in-process `TunnelDAG` merge in
`CommanderCliProvider._enrich_pam_remote_browser_dag_options()` maps
`allowedSettings.connections` / `sessionRecording` to
`pam_settings.options.remote_browser_isolation` / `graphical_session_recording`
when a `KeeperParams` session and a DAG with `has_graph` are available. If
TunnelDAG is missing or empty, those option fields can still be **dirty** in
`plan` — see P3.1 table below.

Status vocabulary:

- **Import-supported** means the field is rendered into `pam_data` for
  `pam project import` / `pam project extend`, and the generated capability
  mirror shows Commander import surface for that record family.
- **Tuning-supported (offline apply-wired)** means Commander exposes an edit
  flag and the SDK maps the manifest field to argv, resolves live Keeper UIDs
  after rediscovery, and unit-tests `_run_cmd()` execution. Live proof remains
  pending.
- **Unsupported / unknown** means the SDK has no first-class model field, no
  confirmed import key, no edit hook, or no verification path yet.

**`pamRemoteBrowser` — P3.1 bucket (2026-04-28)**

| Manifest path | P3.1 bucket | Readback / notes |
|---------------|-------------|------------------|
| `url` | **import-supported** | Commander `get` exposes `rbiUrl`; `discover()` coalesces to `url` (`_coalesce_pam_remote_browser_url`). No `pam rbi edit` flag for URL changes. |
| `pam_settings.options.remote_browser_isolation` | **edit-supported-clean** when in-process `KeeperParams` + PAM config DAG `has_graph`; else **edit-supported-dirty** | Merged from `TunnelDAG` `allowedSettings.connections` in `_enrich_pam_remote_browser_dag_options` (not from raw `get` tri-state alone). |
| `pam_settings.options.graphical_session_recording` | same split | Merged from `allowedSettings.sessionRecording` in the same hook. |
| `pam_settings.connection.*` (typed `pamRemoteBrowserSettings`) | per-row below | Lifted in `_merge_pam_remote_browser_from_get_payload` where Commander returns the typed object. Live smoke covers `protocol`, URL navigation, copy/paste, and cert-ignore false values; list-shaped Commander flags stay **edit-supported-dirty** until the manifest model is list-native. |

| Field | Manifest path | Current status | Commander command / hook | Caveat |
|-------|---------------|----------------|---------------------------|--------|
| PAM config binding | `resources[].pam_configuration_uid_ref` | Tuning-supported (offline apply-wired) | `pam connection edit --configuration`; `pam rbi edit --configuration` | Provider resolves live Keeper UID after rediscovery; live proof pending. |
| Connections toggle | `resources[].pam_settings.options.connections` | Import-supported + tuning-supported (offline apply-wired) | `pam project import/extend`; `pam connection edit --connections` | Offline apply wiring only; live proof pending. |
| Graphical recording | `resources[].pam_settings.options.graphical_session_recording` | Import-supported + tuning-supported (offline apply-wired) | `pam project import/extend`; `pam connection edit --connections-recording` | Commander flag name says connection recording; manifest name says graphical recording. |
| Text/key recording | `resources[].pam_settings.options.text_session_recording` | Import-supported + tuning-supported (offline apply-wired) | `pam project import/extend`; `pam connection edit --typescript-recording` | Commander flag spelling is `--typescript-recording`; live proof pending. |
| Connection protocol | `resources[].pam_settings.connection.protocol` | Import-supported + tuning-supported (offline apply-wired) | `pam project import/extend`; `pam connection edit --protocol` | Applies to resource connection settings, not `pamRemoteBrowser` URL creation. |
| Connection override port | `resources[].pam_settings.connection.port` | Import-supported + tuning-supported (offline apply-wired) | `pam project import/extend`; `pam connection edit --connections-override-port` | SDK stringifies ints before argv execution. |
| Admin credential | `resources[].pam_settings.connection.administrative_credentials_uid_ref` | Import-supported + tuning-supported (offline apply-wired) | `pam project import/extend`; `pam connection edit --admin-user` | Provider fails loudly if the referenced credential cannot be resolved after rediscovery. |
| Launch credential | `resources[].pam_settings.connection.launch_credentials_uid_ref` | Import-supported + tuning-supported (offline apply-wired) | `pam project import/extend`; `pam connection edit --launch-user` | Provider fails loudly if the referenced credential cannot be resolved after rediscovery. |
| Key-event recording | `resources[].pam_settings.connection.recording_include_keys` | Import-supported + tuning-supported (offline apply-wired) | `pam project import/extend`; `pam connection edit --key-events` | Boolean maps to `on` / `off`. |
| Supply user | `resources[].pam_settings.connection.allow_supply_user` | Import-supported only | `pam project import/extend` | No `pam connection edit` flag in the pinned Commander matrix. |
| Copy / paste controls | `resources[].pam_settings.connection.disable_copy`, `disable_paste` | Import-supported only for non-RBI resources | `pam project import/extend` | `pam connection edit` has no copy/paste flags; RBI uses separate inverse flags below. |
| SFTP block | `resources[].pam_settings.connection.sftp.*` | Import-supported only | `pam project import/extend` | No post-import edit flag in the pinned Commander matrix. |
| Port forward | `resources[].pam_settings.port_forward.port`, `reuse_port` | Import-supported only | `pam project import/extend` | No post-import edit flag in the pinned Commander matrix. |
| RBI URL | `resources[type=pamRemoteBrowser].url` | P3.1: **import-supported** | `pam project import/extend` (typed `rbiUrl` read) | `pam rbi edit` has no URL flag. See P3.1 table above. |
| RBI enablement | `resources[type=pamRemoteBrowser].pam_settings.options.remote_browser_isolation` | P3.1: **edit-supported-clean** (DAG) or **edit-supported-dirty** | `pam rbi edit --remote-browser-isolation` | When TunnelDAG is available, merged in `discover()`. If DAG has no graph, re-plan can stay dirty. |
| RBI recording | `resources[type=pamRemoteBrowser].pam_settings.options.graphical_session_recording` | P3.1: **edit-supported-clean** (DAG) or **edit-supported-dirty** | `pam rbi edit --connections-recording` | Same as isolation row. |
| RBI autofill credential | `resources[type=pamRemoteBrowser].pam_settings.connection.autofill_credentials_uid_ref` | P3.1: **edit-supported-clean** when Commander `get` returns typed `httpCredentialsUid`; offline apply-wired | `pam rbi edit --autofill-credentials` | Provider fails loudly if the referenced credential cannot be resolved after rediscovery. Focused live proof still pending. |
| RBI autofill targets | `resources[type=pamRemoteBrowser].pam_settings.connection.autofill_targets` | P3.1: **edit-supported-dirty** | `pam rbi edit --autofill-targets` | Commander supports repeated flags; current manifest model is scalar and no clean list-native readback claim exists. |
| RBI URL navigation | `resources[type=pamRemoteBrowser].pam_settings.connection.allow_url_manipulation` | P3.1: **edit-supported-clean** for typed `pamRemoteBrowserSettings`; smoke-covered false value | `pam rbi edit --allow-url-navigation` | Boolean maps to `on` / `off`. |
| RBI allowed URLs | `resources[type=pamRemoteBrowser].pam_settings.connection.allowed_url_patterns` | P3.1: **edit-supported-dirty** until list-native schema/readback proof | `pam rbi edit --allowed-urls` | Commander supports repeated flags; current manifest model is scalar. |
| RBI allowed resource URLs | `resources[type=pamRemoteBrowser].pam_settings.connection.allowed_resource_url_patterns` | P3.1: **edit-supported-dirty** until list-native schema/readback proof | `pam rbi edit --allowed-resource-urls` | Commander supports repeated flags; current manifest model is scalar. |
| RBI key-event recording | `resources[type=pamRemoteBrowser].pam_settings.connection.recording_include_keys` | P3.1: **edit-supported-clean** when Commander `get` returns typed `recordingIncludeKeys`; offline apply-wired | `pam rbi edit --key-events` | Boolean maps to `on` / `off`. Focused live proof still pending. |
| RBI copy control | `resources[type=pamRemoteBrowser].pam_settings.connection.disable_copy` | P3.1: **edit-supported-clean** for typed `pamRemoteBrowserSettings`; smoke-covered false value | `pam rbi edit --allow-copy` | Polarity is inverted: `disable_copy: true` -> `--allow-copy off`. |
| RBI paste control | `resources[type=pamRemoteBrowser].pam_settings.connection.disable_paste` | P3.1: **edit-supported-clean** for typed `pamRemoteBrowserSettings`; smoke-covered false value | `pam rbi edit --allow-paste` | Polarity is inverted: `disable_paste: true` -> `--allow-paste off`. |
| RBI certificate ignore | `resources[type=pamRemoteBrowser].pam_settings.connection.ignore_server_cert` | P3.1: **edit-supported-clean** for typed `pamRemoteBrowserSettings`; smoke-covered false value | `pam rbi edit --ignore-server-cert` | Boolean maps to `on` / `off`. |
| RBI protocol | `resources[type=pamRemoteBrowser].pam_settings.connection.protocol` | P3.1: **upstream-gap** for tunability; fixed `http` import/readback only | None in pinned `pam rbi edit` flags | Model fixes this to `http`; do not claim post-import tunability. |
| RBI audio controls | no first-class manifest path today | P3.1: **upstream-gap** | `pam rbi edit --disable-audio`, `--audio-bit-depth`, `--audio-channels`, `--audio-sample-rate` | Commander exposes flags, but the SDK model/schema does not expose typed fields yet. |

### Capabilities we explicitly DO NOT use

| command | reason |
|---------|--------|
| `pam project export` | **does not exist** in `17.2.13+` (confirmed: `commands.py::commands` registers only `import` and `extend`). Export is synthesised by iterating `get` + `ls`. |
| `pam project remove` / `destroy` | **does not exist**. Destroy is per-record via `rm --force`. |
| `record-update` via subprocess | version-fragile (see above); in-process API used instead. |
| Interactive `keeper login` / `keeper sync-down` | subprocess would prompt; `deploy_watcher.keeper_login()` handles both via `KeeperParams`. |

## Verification on a fresh workstation

```bash
# 1. The binary must be on PATH and respond to --version
keeper --version  # expect ≥ 17.1.14, preferably 17.2.13+

# 2. The Python module must match (install with pipx so CLI still works)
python3 -m keepercommander --version  # expect 17.2.13+

# 3. JSON output must be wired for PAM listings
keeper pam gateway list --format json | jq .gateways | head
keeper pam config list --format json | jq .configurations | head

# 4. The in-process login helper must resolve
echo "KEEPER_SDK_LOGIN_HELPER=$KEEPER_SDK_LOGIN_HELPER"
# must point at a Python file exposing load_keeper_creds() + keeper_login()
```

If any of these fail, `keeper-sdk apply --provider commander` will raise a
`CapabilityError` with a pointer back to this doc.

## Pin churn policy

- **Patch bumps** (`17.2.x → 17.2.y`): re-run the smoke test; no code change
  unless an error appears. Record date + HEAD in `AUDIT.md`.
- **Minor bumps** (`17.2.x → 17.3.x`): re-read this page; diff
  `keepercommander/commands/pam_import/` and `commands/discoveryrotation.py`
  against the last-pinned HEAD; update capability table.
- **Major bumps** (`17.x → 18.x`): full review sweep — expect renames of the
  in-process classes we import by qualified path.

## Automated capability mirror

The sibling [`keeper-pam-declarative`](../../keeper-pam-declarative) repo used
to be the forward-looking Design of Record. As of 2026-04-24 it is a
**capability mirror** — its contents track what Commander actually ships,
and the authoritative extract lives here in this repo:

- [`docs/CAPABILITY_MATRIX.md`](./CAPABILITY_MATRIX.md) — human-readable
  surface (registered commands, argparse flags, enforcements, record-type
  field sets).
- [`docs/capability-snapshot.json`](./capability-snapshot.json) —
  machine-readable companion, used by CI.

Both are regenerated by `scripts/sync_upstream.py` from a local Commander
checkout. The SHA that was used for the current check-in is pinned in
[`.commander-pin`](../.commander-pin) at the repo root; CI clones
`Keeper-Security/Commander` at that SHA and runs
`sync_upstream.py --check` — any drift fails the build. To bump:

```bash
cd path/to/Commander && git fetch && git checkout <new-sha>
cd path/to/declarative-sdk-for-k
echo <new-sha> > .commander-pin
python scripts/sync_upstream.py
git add .commander-pin docs/CAPABILITY_MATRIX.md docs/capability-snapshot.json
git commit -m "chore(upstream): bump Commander pin to <new-sha>"
```

See [`../keeper-pam-declarative/DRIFT_POLICY.md`](../../keeper-pam-declarative/DRIFT_POLICY.md)
for the policy governing when and how this pin is moved.
