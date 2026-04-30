# Issue #6 / Job E: JIT Support Boundary

## Resolution

Resolved on 2026-04-30.

Pinned Commander 17.2.16 contains the `pam project import` and
`pam project extend` writers that persist `jit_settings` for PAM resources.
DSK already runs those Commander command classes in-process, so JIT support is
classified as supported for the import/extend lifecycle path.

## Supported Scope

- `pam_settings.options.jit_settings` on supported PAM resources.
- Create/update flows that go through `pam project import` or
  `pam project extend`.
- Directory JIT references rendered from `pam_directory_uid_ref` to Commander's
  `pam_directory_record` import key.

## Boundaries That Remain

- No standalone `pam jit` edit command exists in Commander 17.2.16.
- DSK does not directly mutate the PAM DAG.
- `pamRemoteBrowser` still rejects JIT via semantic validation.
- Support claims beyond import/extend need a dedicated live smoke.

## Code State

- `keeper_sdk/core/preview.py` no longer preview-gates `jit_settings`.
- `keeper_sdk/providers/commander_cli.py` no longer emits a JIT capability
  conflict for Commander.
- `keeper_sdk/core/normalize.py` performs the JIT-specific directory-reference
  rewrite needed by Commander import/extend.
