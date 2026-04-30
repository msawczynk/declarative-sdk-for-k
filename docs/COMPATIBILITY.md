# Compatibility matrix

This page is the authoritative reference for which Python versions, Keeper Commander
releases, operating systems, and tenant configurations work with `declarative-sdk-for-k`.

**SDK version covered:** v2.0.0 (`pyproject.toml` classifiers and `requires-python` gate)

---

## 1. Python version compatibility

| Python | DSK v2.0.0 | Notes |
|--------|-----------|-------|
| 3.13 | ✅ Tested | CI green (ubuntu-latest) |
| 3.12 | ✅ Tested | CI green (ubuntu-latest) |
| 3.11 | ✅ Tested | CI green (ubuntu-latest); minimum supported |
| 3.10 | ❌ Not supported | `requires-python = ">=3.11"` hard gate in `pyproject.toml`; f-string syntax used in SDK requires 3.11+ |
| <3.10 | ❌ Not supported | — |

`pyproject.toml` enforces the floor at install time; attempting `pip install` on
Python 3.10 or older will raise a resolver error before any SDK code runs.

---

## 2. Keeper Commander compatibility

| Commander version | DSK v2.0.0 | Notes |
|------------------|-----------|-------|
| 17.2.16 | ✅ Tested (floor) | Minimum supported; `CommanderCliProvider.apply_plan()` reads `importlib.metadata.version("keepercommander")` and raises `CapabilityError` if installed wheel is below this floor |
| 17.2.x (>16) | ✅ Expected | Same API surface as 17.2.16; no known breaking changes on the `release` branch |
| 17.3.x | ⚠️ Untested | May work; report issues. Review `keepercommander/commands/pam_import/` and `commands/discoveryrotation.py` diffs before upgrading |
| <17.2.16 | ❌ Not supported | Missing `pam gateway list --format json`, `pam config list --format json`, and in-process `PAMProjectImportCommand` signatures required by the SDK |
| 18.x | ❌ Blocked | Hard upper ceiling `<18` in `pyproject.toml`; expect in-process class renames on major bump |

### Commander features required by DSK

The SDK calls the following Commander surfaces. See `docs/COMMANDER.md` for the
full capability breakdown and `P3.1` readback bucket definitions.

**Subprocess (`keeper` binary ≥17.2.16 recommended):**

| Command | Used for |
|---------|---------|
| `keeper ls <folder_uid> --format json` | `discover` folder listing |
| `keeper get <uid> --format json` | Record fetch for discover + export |
| `keeper mkdir -uf/-sf …` | Scaffolding PAM Environments folder tree |
| `keeper rm --force <uid>` | Delete orphaned managed records (`apply --allow-delete`) |
| `keeper pam gateway list --format json` | Resolve `mode: reference_existing` gateway UID (17.2.16+) |
| `keeper pam config list --format json` | Resolve reference-existing PAM configuration UID (17.2.16+) |
| `keeper enterprise-info -n/-u/-r/-t -v --format json` | `keeper-enterprise.v1` discover; teams/roles/nodes |
| `keeper secrets-manager share add …` | Bind scaffolded shared folders to gateway KSM app |

**In-process (`keepercommander` Python module):**

| Class / function | Used for |
|-----------------|---------|
| `PAMProjectImportCommand.execute` | Create PAM project scaffold |
| `PAMProjectExtendCommand.execute` | Add resources to existing configuration |
| `api.login` (via `deploy_watcher.py`) | Bootstrap `KeeperParams` for the provider |
| `record_management.update_record` | Write `keeper_declarative_manager` ownership marker |
| `api.query_enterprise` | MSP discover (managed companies slice) |

**Known upstream gaps (exit 5 + `next_action` on stderr):**

| Gap | Status | Workaround |
|-----|--------|-----------|
| `pam rotation info --format=json` | Not available in any 17.x release | Use `keeper pam rotation info` (human-readable); schedule rotation via admin console |
| Standalone JIT edit | No dedicated `pam jit edit` in Commander | Use manifest import/extend lifecycle for supported PAM resources |
| MSP apply (MC create/update/delete) | Requires tenant `msp_permits.allowed_mc_products` | Run `dsk plan --json`; apply via Keeper admin console |
| KSM token/new-share/config-output/app-metadata update | No stable programmatic Commander surface | Use Secrets Manager console |

See `docs/COMMANDER.md` for the complete gap table and Commander pin-churn policy.

---

## 3. Operating system compatibility

| OS | Status | Notes |
|----|--------|-------|
| macOS (Apple Silicon + Intel) | ✅ Tested | Primary development environment |
| Linux (Ubuntu 22.04+) | ✅ Tested | CI runner (ubuntu-latest) |
| Windows | ⚠️ Untested | No CI coverage; PRs welcome. Subprocess shelling to `keeper` binary should work if binary is on PATH, but path separators and shell quoting are untested |

---

## 4. MCP server compatibility

`dsk-mcp` (`keeper_sdk.mcp:main`) exposes a standard MCP stdio server.

| Dimension | Details |
|-----------|---------|
| Transport | `stdio` (default for `dsk-mcp`) |
| Protocol | MCP (Model Context Protocol) |
| Compatible clients | Any MCP-compliant client: Claude Desktop, Cursor, custom MCP harnesses |
| Package | `mcp[cli]` — install separately if using the MCP server (not listed in default `pyproject.toml` dependencies); see `docs/MCP_SERVER.md` |

---

## 5. Keeper tenant requirements

| Feature / manifest family | Tenant requirement |
|--------------------------|-------------------|
| `pam-environment.v1` | PAM add-on enabled on tenant |
| `msp-environment.v1` | MSP license + `msp_permits.allowed_mc_products`; MSP admin login required for `validate --online` |
| `keeper-enterprise.v1` | Enterprise license; `enterprise-info` access |
| `keeper-vault.v1` | Any tier; `login` record type |
| `keeper-ksm.v1` | KSM (Secrets Manager) add-on enabled |

---

## 6. Dependency floor summary

| Package | Minimum | Ceiling | Notes |
|---------|---------|---------|-------|
| `keepercommander` | 17.2.16 | <18 | Hard gate; enforced at runtime by `CommanderCliProvider` |
| `click` | 8.1 | — | CLI framework |
| `pydantic` | 2.0 | — | Manifest models |
| `networkx` | 3.0 | — | DAG / graph operations |
| `pyyaml` | 6.0 | — | Manifest parsing |
| `rich` | 13.0 | — | Terminal renderer |
| `jsonschema` | 4.21 | — | Schema validation |
| `pyotp` | latest | — | TOTP auth helper |
| `keeper-secrets-manager-core` | 17.2.0 | <18 | Optional (`ksm` extra) |

---

## 7. Known upstream gaps (reference)

Short list; see `docs/COMMANDER.md` § "Known Commander gaps affecting DSK" for the
authoritative table with workarounds.

- `pam rotation info --format=json` — not available in any Commander 17.x
- MSP apply — requires tenant MSP product permit
- KSM token/new-share/config-output/app-metadata update — exit 5 upstream-gap; use console
- `pam project export` — does not exist; DSK synthesises via `get` + `ls`
