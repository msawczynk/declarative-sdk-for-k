# JIT Design

Status: `upstream-gap` confirmed on 2026-04-29.

Scope: W8 source audit for the `pam-environment.v1` manifest key
`pam_settings.options.jit_settings`.

## Decision

Keep JIT preview-gated. Do not wire an SDK JIT apply path in this release.

Current classification is `upstream-gap`, not merely `design-boundary`.
The SDK has a manifest shape for JIT, but the pinned Commander surface does
not expose a stable JIT edit command or equivalent write/readback contract for
existing records. The only known writer path is import/extend internals that
mutate the PAM DAG.

Recommended issue action: close GitHub #6 with the `upstream-gap` label and
link this document plus `docs/ISSUE_6_JIT_SUPPORT_BOUNDARY.md`.

## Repo Audit

Audit terms:

- `jit_settings`
- `JIT`
- `just_in_time`

Results:

| Area | Evidence | Meaning |
|------|----------|---------|
| Manifest model | `keeper_sdk/core/models.py::JitSettings`; `ResourceOptions.jit_settings` | DSK can parse the declarative shape. |
| JSON schema | `keeper_sdk/core/schemas/pam-environment.v1.schema.json` `$defs.jit_settings` | Schema accepts the key. |
| Preview gate | `keeper_sdk/core/preview.py::PREVIEW_KEYS` | `validate` rejects JIT unless `DSK_PREVIEW=1`. |
| Semantic rule | `keeper_sdk/core/rules.py` | `pamRemoteBrowser` cannot declare `jit_settings`. |
| Commander provider gate | `keeper_sdk/providers/commander_cli.py::_UNSUPPORTED_CAPABILITY_HINTS` | Provider reports a JIT capability conflict and names the missing hook. |
| Tests/fixtures | `tests/test_preview_gate.py`, `tests/test_rules.py`, `tests/fixtures/examples/full-local/environment.yaml` | Current behavior is pinned as unsupported/preview. |
| Existing audit note | `docs/ISSUE_6_JIT_SUPPORT_BOUNDARY.md` | Prior Commander-source audit already found import/extend DAG internals only. |
| `just_in_time` | no repo hits outside this audit document | No alternate manifest spelling exists. |

## Commander Surface

`docs/COMMANDER.md` lists the Commander surfaces the SDK relies on. No JIT
command or flag appears there.

The generated PAM command matrix in `docs/CAPABILITY_MATRIX.md` registers:

- `pam project import`
- `pam project extend`
- `pam rbi edit`

It does not register:

- `pam jit`
- `pam jit edit`
- any `pam connection edit` JIT flag
- any `pam rbi edit` JIT flag

The older source audit in `docs/ISSUE_6_JIT_SUPPORT_BOUNDARY.md` found
launch-only JIT reads (`pam launch --jit`) and import/extend helper internals
that write `jit_settings` DAG data. Those internals are not a stable DSK apply
contract because they bypass a dedicated Commander edit/readback API for
existing records.

## Current DSK Behavior

`jit_settings` currently behaves as a preview-gated `CapabilityError` path:

1. Without `DSK_PREVIEW=1`, schema load fails through the preview gate.
2. With `DSK_PREVIEW=1`, the Commander provider still classifies the manifest
   as unsupported and surfaces a conflict/`CapabilityError`.
3. No JIT mutation is attempted by the SDK.

The provider conflict text names the current missing hook as:

```text
jit_settings (per-resource or per-config) is not implemented
(Commander hook: `pam_launch/jit.py + DAG jit_settings writer`)
```

That hook name is intentionally not a support claim. It records where Commander
currently hides the behavior, not what DSK is allowed to drive.

## Gate To Remove Preview

Remove the preview gate only after all of these are true:

1. Commander exposes `pam jit`, `pam <resource> jit edit`, or an equivalent
   supported API for existing records.
2. The writer handles create/update without direct SDK DAG writes.
3. The readback path returns enough state for a clean re-plan.
4. Domain JIT links are proven, including the directory relationship now
   written by import/extend internals.
5. A sanctioned live smoke proves write -> discover -> clean re-plan -> destroy.
6. Docs, tests, provider conflict rows, and preview gates are updated in the
   same change.

Until then, `jit_settings` stays preview-gated and #6 stays closed as an
upstream gap rather than open-ended SDK implementation work.
