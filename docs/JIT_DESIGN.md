# JIT Design

Status: `supported` for the `pam project import` / `pam project extend` path as
of 2026-04-30.

Scope: the `pam-environment.v1` manifest key
`pam_settings.options.jit_settings` for PAM resources whose lifecycle already
routes through Commander project import/extend.

## Decision

JIT is no longer classified as an upstream gap for create/update flows that DSK
already applies through `pam project import` and `pam project extend`.
Commander 17.2.16 contains the import/extend writers that persist
`jit_settings` into the PAM DAG, including the domain link when
`pam_directory_uid_ref` is supplied.

DSK support is intentionally scoped:

- Supported: declarative JIT settings rendered into the project import/extend
  JSON payload for PAM resource create/update.
- Supported: `pam_directory_uid_ref` is rendered as Commander's expected
  `pam_directory_record` key.
- Not claimed: a standalone post-import `pam jit edit` writer. Commander does
  not expose one in 17.2.16.
- Not claimed: `pamRemoteBrowser` JIT; semantic rules still reject that shape.

## Commander Surface

Commander 17.2.16 registers `pam project import` and `pam project extend`.
Those command classes include the JIT DAG writer used by Keeper's project import
flow. DSK already invokes both commands in-process from
`keeper_sdk/providers/commander_cli.py`, so no direct SDK DAG mutation is
needed.

There is still no separate `pam jit` command. Future post-import JIT-only edits
should use a dedicated Commander writer if one appears in a later release.

## DSK Behavior

`jit_settings` is removed from the preview and Commander unsupported-capability
gates. A manifest containing JIT settings now validates and plans as an ordinary
PAM resource change.

During import payload rendering, DSK maps:

- `pam_directory_uid_ref: <uid_ref>` -> `pam_directory_record: <directory title>`
- Other JIT keys retain the snake_case names Commander import/extend expects.

## Remaining Caveats

Support depends on the normal PAM import/extend readback contract. A focused
live smoke should still be used before broadening support claims to new JIT
resource combinations or future standalone edit flows.
