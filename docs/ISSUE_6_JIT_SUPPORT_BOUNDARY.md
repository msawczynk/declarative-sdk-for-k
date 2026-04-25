# Issue #6 / Job E: JIT Support Boundary

## Decision

Keep `jit_settings` preview-gated in this SDK release.

Pinned Commander `631505404f4881f35ef4e17356d71cba556281b9` can read JIT settings for `pam launch --jit` and can write JIT settings during `pam project import` / `pam project extend`, but it does not expose a dedicated safe writer path for existing records that avoids direct DAG mutation semantics. The SDK should not remove the support gate until a post-import/update contract is proven end-to-end, including domain JIT links and drift reconciliation.

Classification: upstream gap for a stable JIT edit surface; SDK mapper work is obvious but not enough to wire apply safely.

## SDK Boundary Today

- `keeper_sdk/core/preview.py` keeps `jit_settings` in `PREVIEW_KEYS` as "planned for 1.2".
- `keeper_sdk/providers/commander_cli.py` reports `jit_settings` as an unsupported Commander-provider capability and names `pam_launch/jit.py + DAG jit_settings writer` as the hook.
- `keeper_sdk/core/models.py` and `keeper_sdk/core/schemas/pam-environment.v1.schema.json` already model the declarative shape:
  - `create_ephemeral`
  - `elevate`
  - `elevation_method`
  - `elevation_string`
  - `base_distinguished_name`
  - `ephemeral_account_type`
  - `pam_directory_uid_ref`

No support gate was removed for this investigation.

## Pinned Commander Evidence

Pinned Commander source inspected from `.commander-pin`:

`keepercommander/commands/pam_launch/jit.py`

- Module docstring states Web Vault authoritative storage is an encrypted DAG DATA edge at path `jit_settings`, with camelCase keys, and the declarative mirror is `pamSettings.options.jit_settings`.
- Public symbols are read/launch oriented:
  - `normalize_jit_settings`
  - `derive_jit_mode`
  - `load_jit_settings`
  - `build_ephemeral_payload`
  - `build_elevation_payload`
  - `provisions_credential`
- `load_jit_settings` reads DAG first via `get_resource_jit_settings`, then falls back to the typed field mirror. It does not write.

`keepercommander/commands/pam_import/base.py`

- `DagJitSettingsObject.load` parses snake_case JSON fields from `pamSettings.options.jit_settings`.
- `DagJitSettingsObject.to_dag_dict` maps to DAG camelCase:
  - `create_ephemeral` -> `createEphemeral`
  - `elevate` -> `elevate`
  - `elevation_method` -> `elevationMethod`
  - `elevation_string` -> `elevationString`
  - `base_distinguished_name` -> `baseDistinguishedName`
  - `ephemeral_account_type` -> `ephemeralAccountType`
- `pam_directory_record` is parsed separately as a title reference and is not included in the DATA payload.

`keepercommander/commands/pam_import/keeper_ai_settings.py`

- `set_resource_jit_settings(params, resource_uid, settings, config_uid=None)` writes JIT by loading the PAM DAG, deactivating any active `jit_settings` DATA edge, calling `resource_vertex.add_data(... path='jit_settings' ...)`, then `linking_dag.save()`.
- This is a direct DAG mutation helper, not a stable CLI/API writer surface.

`keepercommander/commands/pam_import/edit.py`

- `PAMProjectImportCommand` resolves `jit_settings.pam_directory_record` to `pam_directory_uid`.
- It calls `set_resource_jit_settings(...)` after `tdag.set_resource_allowed(...)`.
- For domain JIT, it links the resource vertex to the directory vertex with `machine_vertex.belongs_to(dir_vertex, EdgeType.LINK, path="domain", content={})`, then saves the DAG.

`keepercommander/commands/pam_import/extend.py`

- `PAMProjectExtendCommand` repeats the same pattern for extending existing projects:
  - resolve `jit_settings.pam_directory_record`
  - call `set_resource_jit_settings(...)`
  - write the domain `EdgeType.LINK` with `path="domain"`

`keepercommander/commands/pam_import/commands.py`

- `PAMProjectCommand` registers only `import` and `extend`.
- No `jit`, `env apply`, or standalone JIT edit command is registered under `pam project`.

Repo-wide pinned search:

- `--jit` appears on launch paths only (`pam_launch/launch.py`, `pam_launch/terminal_connection.py`).
- `set_resource_jit_settings` appears only in `pam_import` paths.
- `pam env apply` appears only in comments/help text, not as a registered command.

## Pure Mapper Candidate

The obvious SDK-side pure mapper is small and should remain un-wired until the provider contract is proven:

```python
def jit_settings_to_commander_import(settings: Mapping[str, Any], refs: Mapping[str, str]) -> dict[str, Any]:
    out = {
        "create_ephemeral": settings.get("create_ephemeral"),
        "elevate": settings.get("elevate"),
        "elevation_method": settings.get("elevation_method"),
        "elevation_string": settings.get("elevation_string"),
        "base_distinguished_name": settings.get("base_distinguished_name"),
        "ephemeral_account_type": settings.get("ephemeral_account_type"),
    }
    if settings.get("pam_directory_uid_ref"):
        out["pam_directory_record"] = refs[settings["pam_directory_uid_ref"]]
    return {k: v for k, v in out.items() if v not in (None, "")}
```

Important boundary: `keeper_sdk/core/normalize.py` currently rewrites `pam_directory_uid_ref` generically to `pam_directory`, but Commander JIT import logic expects `pam_directory_record`. Any future mapper needs a JIT-specific rewrite for this key. The domain link still depends on Commander import/extend internals writing `EdgeType.LINK(path="domain")`.

## Next Step

Do not wire JIT apply yet. Keep the preview gate and provider conflict. Future implementation should start with offline mapper tests, then a mocked Commander import/extend contract test, then one live smoke in a disposable PAM config before removing `jit_settings` from preview.
