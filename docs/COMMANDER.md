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
import`/`extend`, `_write_marker`). If `pip show keepercommander` reports an
older version, `apply` will fail early with a `CapabilityError`.

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
