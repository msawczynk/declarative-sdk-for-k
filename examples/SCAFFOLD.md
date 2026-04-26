# `examples/` — canonical minimal manifests

Root `*.yaml` files are one PAM resource type each, minimal shape, valid against
`keeper_sdk/core/schemas/pam-environment.v1.schema.json`.

`examples/scaffold_only/*.yaml` are **non-PAM** packaged-schema samples
(`keeper-vault`, `keeper-vault-sharing`, …): `dsk validate` only (no mock
`plan` — `load_manifest` stays PAM-only until Phase 1). CI validates them in the
same offline gate as root examples.

CI validates every file offline AND `--provider mock`-plans them clean
(`.github/workflows/ci.yml` examples job + `tests/test_smoke_scenarios.py`
shape coverage).

## Files

| File | Resource type | Notes |
|---|---|---|
| `pamMachine.yaml` | `pamMachine` | Reference shape — copy this for new examples. |
| `pamDatabase.yaml` | `pamDatabase` | Includes `database_type` to satisfy verifier. |
| `pamDirectory.yaml` | `pamDirectory` | Includes directory-specific binding fields. |
| `pamRemoteBrowser.yaml` | `pamRemoteBrowser` | Connection settings only — RBI tri-state and audio keys remain preview-gated. |

### `scaffold_only/` (schema gate only)

| File | `schema:` | Notes |
|------|-----------|--------|
| `vaultMinimal.yaml` | `keeper-vault.v1` | Empty `records` — offline CI + `dsk validate --json`. |
| `vaultSharingMinimal.yaml` | `keeper-vault-sharing.v1` | Empty sharing blocks (defaults). |

## Where to land new work

| Change | File | Sibling to copy |
|---|---|---|
| New example resource type | `<name>.yaml` + add to CI examples job + `tests/test_smoke_scenarios.py` shape | `pamMachine.yaml` |

## Hard rules

- Each example MUST validate clean WITHOUT `DSK_PREVIEW=1`.
- No `rotation_settings`, `jit_settings`, `gateway.mode: create`, top-level `projects[]` (would need preview gate → ineligible).
- No real secrets. Use placeholder strings; redaction patterns will catch real ones in CI.
- Field set kept minimal — full coverage lives in tests + smoke scenarios.

## Reconciliation

`V1_GA_CHECKLIST.md` § 1 row "Examples exist and CI validates them offline +
mock-plans them" → SHIPPED. All 4 example files match the latest schema and
preview-gate contract.

## Note on `examples/invalid/`

The DOR ships an `examples/invalid/*.yaml` corpus. This repo's
`tests/test_schema.py` (W9) auto-discovers them at collection time. Today
that corpus lives in the upstream sibling repo and is mirrored as needed
into `tests/fixtures/examples/`. New invalid fixtures land in `tests/fixtures/`
or upstream — NOT here, because `examples/` must remain "all green" inputs.
