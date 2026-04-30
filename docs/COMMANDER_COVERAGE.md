# Commander Feature Coverage

> For the Commander dependency pin, version requirements, and raw capability
> surface, see [COMMANDER.md](COMMANDER.md).  
> This document is the **operations reference**: which Commander commands DSK
> invokes for each manifest family, which CRUD operations are supported,
> and what is explicitly not covered.

---

## 1. Commander command coverage table

| DSK Family | Commander commands used | Invocation mode | DSK operations |
|---|---|---|---|
| `pam-environment.v1` | `pam project import`, `pam project extend`, `pam gateway list/new/edit/remove`, `pam config list --format json`, `pam rotation list --record-uid <uid> --format json`, `pam connection edit`, `pam rbi edit`, `pam rotation edit`, `ls <folder> --format json`, `get <uid> --format json`, `rm --force <uid>` | In-process (import/extend/gateway lifecycle/rotation/edit) + subprocess (ls/get/rm/list fallbacks) | validate, plan, diff, apply, import, export |
| `keeper-vault.v1` | `ls <folder_uid> --format json`, `get <uid> --format json`, `rm --force <uid>` + in-process `RecordAddCommand`, `record_management.update_record` | In-process (add/marker) + subprocess (ls/get/rm) | validate, plan, diff, apply |
| `keeper-vault-sharing.v1` | `mkdir -uf <path>`, `mkdir -sf --manage-users --manage-records --can-edit --can-share <path>`, `mv --user-folder/--shared-folder <src> <dst>`, `rmdir -f <path_or_uid>`, `share-record -a grant/revoke -e <email>`, `share-folder`, `secrets-manager share add --app <app> --secret <sf_uid> --editable`, `ls --format json`, `get <sf_uid> --format json` | In-process + subprocess | validate, plan, diff, apply |
| `keeper-ksm.v1` | In-process `KSMCommand.add_new_v5_app(params, name)`, `KSMCommand.remove_v5_app(params, app_name_or_uid, purge, force)`, `KSMCommand.update_app_share(params, secret_uids, app_uid, editable)` | In-process only | validate, plan, apply (app create/delete, existing share editable update) |
| `keeper-enterprise.v1` | `enterprise-info -n -v --format json` (nodes), `enterprise-info -u -v --format json` (users), `enterprise-info -r -v --format json` (roles), `enterprise-info -t -v --format json` (teams) | Subprocess | validate, plan, diff, validate --online |
| `msp-environment.v1` | In-process `api.query_enterprise(params)` for discover; in-process `MSPAddCommand`, `MSPUpdateCommand`, `MSPRemoveCommand` for apply | In-process only | validate, plan, diff, apply (MC create/update/delete with tenant permit) |
| `keeper-workflow.v1` | Commander release surface verified (`pam workflow`) | Not wired yet | validate (schema/model scaffold) |
| `keeper-privileged-access.v1` | Commander release surface verified (`pam access`) | Not wired yet | validate (schema/model scaffold) |
| `keeper-tunnel.v1` | Commander release surface verified (`pam tunnel`) | Not wired yet | validate (schema/model scaffold) |
| `keeper-saas-rotation.v1` | Commander release surface verified (`pam action saas`) | Not wired yet | validate (schema/model scaffold) |

> **Note:** `dsk export` does **not** use `pam project export` — that command does
> not exist in Commander `17.2.16+`. Export is synthesised by iterating `ls` +
> `get` over the project folder.

---

## 2. DSK operations × Commander verb class matrix

| DSK operation | Commander verb class | Mutation? | Notes |
|---|---|---|---|
| `dsk validate` (offline) | None — schema only | No | Safe; no network |
| `dsk validate --online` | `list` / `get` (read-only) | No | Discovers live tenant for reference checks |
| `dsk plan` | `list` / `get` (read-only) | No | Computes delta; no writes |
| `dsk diff` | `list` / `get` (read-only) | No | Field-level diff; no writes |
| `dsk apply` (create) | `pam project import`, `pam gateway new`, `RecordAddCommand`, `mkdir`, `MSPAddCommand`, `KSMCommand.add_new_v5_app` | **Yes** | Creates new resources |
| `dsk apply` (update) | `pam project extend`, `pam gateway edit`, `pam connection edit`, `pam rbi edit`, `pam rotation edit`, `record_management.update_record`, `MSPUpdateCommand`, `KSMCommand.update_app_share` | **Yes** | Modifies existing resources |
| `dsk apply` (delete) | `rm --force <uid>`, `pam gateway remove`, `rmdir -f`, `MSPRemoveCommand`, `KSMCommand.remove_v5_app` | **Yes** | Requires `--allow-delete` for PAM/vault/KSM deletes |
| `dsk import` | `list` / `get` + marker write via `record_management.update_record` | **Yes** (marker write only) | Adopts existing records; no structural change |
| `dsk export` | `ls --format json`, `get --format json` (iterates project folder) | No | Synthesised; no `pam project export` |
| `dsk report password-report` | `security-audit-report` Commander command | No | Read-only; output redacted |
| `dsk report compliance-report` | `compliance-report` Commander command | No | Read-only; output redacted |
| `dsk report security-audit-report` | `security-audit-report` Commander command | No | Read-only; output redacted |

---

## 3. Commander service mode vs CLI mode

DSK supports two invocation modes for the `commander` provider:

### CLI mode (subprocess — default)

- Shells out to the `keeper` binary on `PATH`.
- Used for: `ls`, `get`, `rm`, `mkdir`, `mv`, `rmdir`, `share-record`,
  `share-folder`, `secrets-manager share add`, `pam gateway list`,
  `pam config list`, `pam rotation list`, `enterprise-info`.
- Requires an active `keeper login` session (Commander persists session tokens).
- Timeout: 60 s per command (configurable via `CommanderCliProvider`).

### In-process mode (Python module)

- Imports `keepercommander` directly; reuses the logged-in `KeeperParams` object
  produced by `deploy_watcher.keeper_login()`.
- Used for: `pam project import` / `extend` (cannot resume a subprocess session),
  `pam rotation edit`, `pam connection edit`, `pam rbi edit`,
  `RecordAddCommand` (vault record add), `record_management.update_record`
  (marker writes), `api.query_enterprise` (MSP / enterprise discover),
  `MSPAddCommand` / `MSPUpdateCommand` / `MSPRemoveCommand`,
  `KSMCommand.add_new_v5_app`, `KSMCommand.remove_v5_app`,
  `KSMCommand.update_app_share`, and `pam gateway new/edit/remove`.
- Requires `keepercommander>=17.2.16,<18` installed as a Python module.
  `apply_plan()` gates on this before any mutation.

### Configuration

```bash
# Minimal: env-var credential path (see docs/LOGIN.md for KSM / custom-helper paths)
export KEEPER_EMAIL='you@example.com'
export KEEPER_PASSWORD='...'
export KEEPER_TOTP_SECRET='BASE32SECRET'  # NOT a 6-digit code

# Optional: restrict to a specific session config
export KEEPER_CONFIG='/path/to/keeper-config.json'
export KEEPER_SERVER='keepersecurity.com'

# Optional: custom login helper (KSM pull, device approval, etc.)
export KEEPER_SDK_LOGIN_HELPER=/abs/path/to/helper.py  # overrides above env vars
```

Both modes share the same `KeeperParams` session object; the split is purely
about which Commander Python surface is stable enough to call via subprocess.

---

## 4. Supported operations by resource type

### 4.1 pam-environment.v1

Most PAM resource CRUD routes through `pam project import` (create) or
`pam project extend` (update). Gateway lifecycle is the exception and uses
`pam gateway new/edit/remove`. Discover reads via `ls` + `get` plus gateway /
config list commands; non-gateway delete uses `rm --force`.

| Resource type | Create | Read (discover) | Update | Delete | Import (adopt) |
|---|---|---|---|---|---|
| `pamGateway` | ✅ `pam gateway new` | ✅ `pam gateway list` (for uid resolution) | ✅ `pam gateway edit` | ✅ `pam gateway remove` | ✅ `mode: reference_existing` |
| `pamConfiguration` | ✅ `pam project import` | ✅ `pam config list` + `get` | ✅ `pam project extend` | ✅ `rm --force` | ✅ |
| `pamMachine` | ✅ `pam project import` | ✅ `ls` + `get` | ✅ `pam project extend` + `pam connection edit` | ✅ `rm --force` | ✅ |
| `pamDatabase` | ✅ `pam project import` | ✅ `ls` + `get` | ✅ `pam project extend` + `pam connection edit` | ✅ `rm --force` | ✅ |
| `pamDirectory` | ✅ `pam project import` | ✅ `ls` + `get` | ✅ `pam project extend` + `pam connection edit` | ✅ `rm --force` | ✅ |
| `pamUser` | ✅ `pam project import` | ✅ `ls` + `get` | ✅ `pam project extend` | ✅ `rm --force` | ✅ |
| `pamRemoteBrowser` | ✅ `pam project import` | ✅ `ls` + `get` + TunnelDAG merge | ✅ `pam project extend` + `pam rbi edit` | ✅ `rm --force` | ✅ |

**Post-import field tuning (connection / RBI) — P3.1 readback buckets:**

| Manifest field path | P3.1 bucket | Commander verb |
|---|---|---|
| `resources[].url` (pamRemoteBrowser) | import-supported | `pam project import/extend` |
| `resources[].pam_settings.options.remote_browser_isolation` | edit-supported-clean (when TunnelDAG available) | `pam rbi edit --remote-browser-isolation` |
| `resources[].pam_settings.options.graphical_session_recording` | edit-supported-clean (when TunnelDAG available) | `pam rbi edit --connections-recording` |
| `resources[].pam_settings.connection.autofill_credentials_uid_ref` | edit-supported-clean | `pam rbi edit --autofill-credentials` |
| `resources[].pam_settings.connection.autofill_targets` | edit-supported-dirty | `pam rbi edit --autofill-targets` |
| `resources[].pam_settings.connection.allow_url_manipulation` | edit-supported-clean | `pam rbi edit --allow-url-navigation` |
| `resources[].pam_settings.connection.allowed_url_patterns` | edit-supported-dirty | `pam rbi edit --allowed-urls` |
| `resources[].pam_settings.connection.allowed_resource_url_patterns` | edit-supported-dirty | `pam rbi edit --allowed-resource-urls` |
| `resources[].pam_settings.connection.recording_include_keys` | edit-supported-clean | `pam rbi edit --key-events` |
| `resources[].pam_settings.connection.disable_copy` | edit-supported-clean | `pam rbi edit --allow-copy` (inverted) |
| `resources[].pam_settings.connection.disable_paste` | edit-supported-clean | `pam rbi edit --allow-paste` (inverted) |
| `resources[].pam_settings.connection.ignore_server_cert` | edit-supported-clean | `pam rbi edit --ignore-server-cert` |
| `resources[].pam_settings.connection.protocol` | upstream-gap | None (fixed `http`) |
| `resources[].users[].rotation_settings` | experimental — `DSK_EXPERIMENTAL_ROTATION_APPLY=1` | `pam rotation edit` |

**Rotation scheduling** is gated behind `DSK_EXPERIMENTAL_ROTATION_APPLY=1`.
`pam rotation info --format=json` does not exist in Commander `17.x`; readback
uses the human-readable form and is partial.

---

### 4.2 keeper-vault.v1

Operate on `login`-type records in a scoped shared folder. Other record types
are partially supported via the same path (read works; typed-field write for
non-login types may lose precision).

| Operation | `login` records | Other record types |
|---|---|---|
| Create | ✅ In-process `RecordAddCommand` | ⚠️ Partial — same path, typed-field fidelity varies |
| Read / plan | ✅ `ls` + `get` | ✅ |
| Update (field drift) | ✅ In-process `record_management.update_record` | ⚠️ Partial |
| Marker write | ✅ Custom field via `record_management.update_record` | ✅ |
| Delete | ✅ `rm --force` (requires `--allow-delete`) | ✅ |

`keeper_fill` resource type (W3-AB schema-honesty slice): routed through
dedicated `_vault_add_login_record` / keeper_fill helpers — not the generic
login path.

---

### 4.3 keeper-vault-sharing.v1

| Operation | Status | Commander surface |
|---|---|---|
| Create user folder | ✅ | `mkdir -uf <path>` |
| Create shared folder | ✅ | `mkdir -sf --manage-users --manage-records --can-edit --can-share <path>` |
| Move folder | ✅ | `mv --user-folder/--shared-folder <src> <dst>` |
| Delete folder | ✅ | `rmdir -f <path_or_uid>` |
| Grant share-record | ✅ | `share-record -a grant -e <email>` |
| Revoke share-record | ✅ | `share-record -a revoke -e <email>` |
| Share folder | ✅ | `share-folder` |
| Bind KSM app to shared folder | ✅ | `secrets-manager share add --app <app> --secret <sf_uid> --editable` |
| Discover shared folder | ✅ | `ls --format json`, `get <sf_uid> --format json` |

---

### 4.4 keeper-ksm.v1

| Operation | Status | Commander surface | Notes |
|---|---|---|---|
| App create | ✅ Supported | In-process `KSMCommand.add_new_v5_app(params, name)` | Requires `17.2.16+` |
| App metadata update | ❌ Not supported | No `update_v5_app`; no DSK app-metadata contract | Raises `CapabilityError` |
| App delete | ✅ Supported | In-process `KSMCommand.remove_v5_app(params, app_name_or_uid, purge, force)` | Requires delete row from owned live state |
| Token add | ❌ Upstream-gap | None | Not a stable programmatic surface |
| Existing share editable update | ✅ Supported | In-process `KSMCommand.update_app_share(params, secret_uids, app_uid, editable)` | Existing shares only |
| New record share | ❌ Upstream-gap | No committed DSK create/readback contract in this family | Use Secrets Manager console or sharing family where applicable |
| Config output | ❌ Upstream-gap | None | Use Secrets Manager console |

---

### 4.5 keeper-enterprise.v1

Read-only. No mutations are implemented for enterprise data.

| Resource | Read (discover) | Create | Update | Delete |
|---|---|---|---|---|
| nodes | ✅ `enterprise-info -n -v --format json` | ❌ | ❌ | ❌ |
| users | ✅ `enterprise-info -u -v --format json` | ❌ | ❌ | ❌ |
| roles | ✅ `enterprise-info -r -v --format json` | ❌ | ❌ | ❌ |
| teams | ✅ `enterprise-info -t -v --format json` | ❌ | ❌ | ❌ |
| enforcements | Schema only — no Commander surface wired | ❌ | ❌ | ❌ |

---

### 4.6 msp-environment.v1

MSP discover uses `api.query_enterprise(params)` in-process (not `keeper msp-info`
subprocess). Apply requires MSP admin session and tenant `msp_permits.allowed_mc_products`.

| Operation | Resource type | Status | Commander surface |
|---|---|---|---|
| Discover / plan | `managed_company` | ✅ | In-process `api.query_enterprise` |
| Create | `managed_company` | ✅ (with tenant permit) | In-process `MSPAddCommand.execute` |
| Update | `managed_company` | ✅ (with tenant permit) | In-process `MSPUpdateCommand.execute` |
| Delete | `managed_company` | ✅ (with tenant permit) | In-process `MSPRemoveCommand.execute` |
| Import marker write | `managed_company` | ❌ Not implemented | No stable marker path |
| Non-MC resource types | any | ❌ | Raises `CapabilityError` |


### 4.7 PAM workflow, SaaS rotation, tunnel, and access

Reference-only status for Commander groups adjacent to `pam-environment.v1`; these
are not necessarily wired through the standard import/extend table above.

| Commander surface | Commander availability | DSK status |
|---|---|---|
| `pam workflow` | **17.2.14+** (full stack from **17.2.16**) | `workflow_settings:` colocated extension on PAM resources in progress (**Wave E**). |
| `pam saas` | **17.2.16** | `saas_plugins:` opaque passthrough on `pamUser` in progress (**Wave E**). |
| `pam tunnel` | **17.2.16** | Operation-only; not declarative — explicitly out of scope for DSK plan/apply. |
| `pam access` | **17.2.16** | Operation-only (IdP provisioning flows); out of scope for declarative management. |

---

## 5. Report coverage

| Report | Commander source | Output format | Status |
|---|---|---|---|
| `dsk report password-report` | `security-audit-report` Commander command | Redacted JSON envelope | Supported |
| `dsk report compliance-report` | `compliance-report` Commander command | Redacted JSON envelope | Supported |
| `dsk report security-audit-report` | `security-audit-report` Commander command | Redacted JSON envelope | Supported |

All reports: exit **0** clean, exit **1** on secret leak detection.
`--sanitize-uids` fingerprints UID values; `--quiet` also fingerprints
`record_uid` / `shared_folder_uid` keys. See `AGENTS.md` command table for
per-report flags.

---

## 6. Explicit capability gaps

| Gap | Root cause | Workaround | Tracking |
|---|---|---|---|
| `pam rotation info --format=json` | Not available in any `17.x` release | `keeper pam rotation info` (human-readable); rotation scheduling via admin console | Upstream backlog |
| Rotation scheduling apply | `DSK_EXPERIMENTAL_ROTATION_APPLY` must be set; readback partial | Do not use in production without live proof | Experimental gate |
| KSM token / new share / config-output / app-metadata update management | Not a stable programmatic Commander surface in this family | Keeper Secrets Manager console; `keeper sm token add` interactively | v2+ roadmap |
| MSP apply without tenant permit | `msp_permits.allowed_mc_products` required on tenant | Request MSP permit from Keeper; validate-only with `dsk plan` | Upstream tenant-capability |
| MSP import marker write | No stable marker anchor for managed-company records | Use mock provider for full lifecycle testing | Design pending (`docs/MSP_FAMILY_DESIGN.md`) |
| Enterprise write operations | Commander enterprise API is read-only via DSK | Use Keeper admin console for node/user/role/team mutations | By design (read-only family) |
| `pam project export` | Does not exist in Commander `17.2.16+` | `dsk export <project.json>` synthesises export from `ls` + `get` | N/A — DSK workaround ships |
| `record-update` (subprocess) | Version-fragile typed-field syntax | In-process `record_management.update_record` API used instead | N/A — DSK workaround ships |
| Standalone JIT edit | No dedicated `pam jit edit` Commander surface separate from import/extend | Use manifest import/extend lifecycle for supported PAM resources | Future Commander surface |
| RBI audio controls | Commander exposes flags; no typed manifest field | — | Schema extension candidate |
| `pam rbi edit` autofill-targets (list-native) | Scalar model vs Commander repeated flags | Single-target autofill works; list readback dirty | Schema extension candidate |

---

## 7. Commander version compatibility

| Commander version | DSK behavior |
|---|---|
| `<17.1.14` (binary) | Not supported — JSON output not wired |
| `<17.2.16` (Python module) | `apply_plan()` raises `CapabilityError` before any mutation; `validate` / `plan` / `diff` work |
| `17.2.16` (floor — fully tested) | All supported operations green; reference pin for CI |
| `17.2.x` (>16) | Expected compatible — re-run smoke on each patch bump |
| `17.3.x` | Untested — run `scripts/smoke/smoke.py` and report |
| `>=18` | Blocked — hard ceiling in `pyproject.toml` (`keepercommander<18`) |

Two version concepts apply:

1. **`keeper` binary** (`≥17.1.14`) — used for subprocess calls (`ls`, `get`,
   `rm`, `pam gateway list`, etc.).
2. **`keepercommander` Python module** (`≥17.2.16,<18`) — used for in-process
   calls. `apply_plan()` reads `importlib.metadata.version("keepercommander")`
   and fails fast if the wheel is below the floor, even when the binary is newer.

See [COMMANDER.md](COMMANDER.md) for the exact pin SHA and delta table between
`17.1.14` and `17.2.16`.

---

## 8. Commands DSK explicitly does not use

| Command | Reason |
|---|---|
| `pam project export` | Does not exist in `17.2.16+`; DSK synthesises via `ls` + `get` |
| `pam project remove` / `destroy` | Does not exist; destroy is per-record `rm --force` |
| `record-update` (subprocess) | Version-fragile; in-process API used instead |
| Interactive `keeper login` / `keeper sync-down` | Subprocess prompts interactively; `deploy_watcher.keeper_login()` handles both |
| `msp-down` (subprocess) | In-process `api.query_enterprise` used; operators may run `keeper msp-down` manually to refresh cache |
| `pam rotation info --format=json` | Not available in `17.x`; human-readable fallback only |
| `secrets-manager token add` | Not a stable programmatic surface in `17.x` |

---

## 9. Raw CLI coverage report (auto-generated)

The table below is extracted by `scripts/coverage/commander_coverage.py` from
`docs/capability-snapshot.json` and `commander_cli.py`. It tracks **subprocess
CLI calls only** — in-process API paths (`pam project import/extend`,
`MSPAddCommand`, `KSMCommand`, `RecordAddCommand`, `record_management.*`,
`api.query_enterprise`) are not counted in these numbers.

**24.5% subprocess CLI coverage (13 of 53 registered Commander commands).**
The "not covered" denominator is large because the capability snapshot includes
mirrored surface (automator, scim, trash, enterprise-node/role/team/user,
etc.) that DSK deliberately does not route through. In-process paths cover
the remaining operational surface; see sections 1–4 above for the full picture.

| Command | Covered by DSK | DSK verb | Notes |
|---|---|---|---|
| `get` | ✅ | validate --online / plan / apply | Subprocess |
| `ls` | ✅ | validate --online / plan / apply | Subprocess |
| `mkdir` | ✅ | apply | Subprocess |
| `pam config list` | ✅ | validate --online / plan | Subprocess |
| `pam connection edit` | ✅ | apply | In-process |
| `pam gateway list` | ✅ | validate --online / plan | Subprocess |
| `pam project extend` | ✅ | apply | In-process |
| `pam project import` | ✅ | apply | In-process |
| `pam rbi edit` | ✅ | apply | In-process |
| `record-add` | ✅ | apply | In-process |
| `rm` | ✅ | apply --allow-delete | Subprocess |
| `secrets-manager share add` | ✅ | apply | Subprocess |
| `enterprise-info` | ✅ | validate --online / plan | Subprocess |
| `msp-add` | ✅ (in-process) | apply | Generator marks ❌ — uses in-process `MSPAddCommand` |
| `msp-update` | ✅ (in-process) | apply | Generator marks ❌ — uses in-process `MSPUpdateCommand` |
| `msp-remove` | ✅ (in-process) | apply | Generator marks ❌ — uses in-process `MSPRemoveCommand` |
| `mv` | ✅ (in-process) | apply | Not in generator `COMMAND_ROOTS` |
| `rmdir` | ✅ (in-process) | apply | Not in generator `COMMAND_ROOTS` |
| `share-record` | ✅ (in-process) | apply | Not in generator `COMMAND_ROOTS` |
| `share-folder` | ✅ (in-process) | apply | Not in generator `COMMAND_ROOTS` |
| `record-update` | ❌ (by design) | — | In-process `RecordEditCommand` used instead |
| `pam project export` | ❌ (does not exist) | — | DSK synthesises via `ls` + `get` |
| `automator *`, `scim *`, `trash *` | ❌ | — | Mirrored surface; no DSK lifecycle coverage |

To refresh the raw report:

```bash
python3 scripts/coverage/commander_coverage.py > docs/COMMANDER_COVERAGE.md
```

Note: that command **overwrites** this document. To regenerate the raw section
only without losing sections 1–8, re-run the generator and append from `## Raw`
or use a dedicated output flag when one is added to the script.
