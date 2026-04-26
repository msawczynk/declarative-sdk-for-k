# `examples/` — canonical minimal manifests

Root `*.yaml` files are one PAM resource type each, minimal shape, valid against
`keeper_sdk/core/schemas/pam-environment.v1.schema.json`.

`examples/scaffold_only/*.yaml` are **non-PAM** packaged-schema samples
(`keeper-vault.v1`, `keeper-vault-sharing.v1`, …). **`dsk validate`** runs on them
in CI in the same loop as root `examples/*.yaml` (`.github/workflows/ci.yml`
`examples` job). The **`examples` job’s mock `plan` step** only iterates
`examples/*.yaml` (not `scaffold_only/`); vault **`plan` / `diff` / `apply`** for
`keeper-vault.v1` is exercised in **pytest** (`tests/test_vault_mock_provider.py`,
`tests/test_cli.py`, …) via `load_declarative_manifest` + `MockProvider` /
`CommanderCliProvider` fakes — not omitted from coverage.

## Files

| File | Resource type | Notes |
|---|---|---|
| `pamMachine.yaml` | `pamMachine` | Reference shape — copy this for new examples. |
| `pamDatabase.yaml` | `pamDatabase` | Includes `database_type` to satisfy verifier. |
| `pamDirectory.yaml` | `pamDirectory` | Includes directory-specific binding fields. |
| `pamRemoteBrowser.yaml` | `pamRemoteBrowser` | Connection settings only — RBI tri-state and audio keys remain preview-gated. |

### `scaffold_only/` (packaged families; CI validate)

| File | `schema:` | Notes |
|------|-----------|-------|
| `vaultMinimal.yaml` | `keeper-vault.v1` | Empty `records` — offline `dsk validate` + `dsk validate --json` (`vault_offline`). |
| `vaultOneLogin.yaml` | `keeper-vault.v1` | Single **`login`** row for L1 lab / V8 prep; edit `uid_ref` / titles for your folder. |
| `vaultSharingMinimal.yaml` | `keeper-vault-sharing.v1` | Empty sharing blocks (defaults). |

## Where to land new work

| Change | File | Sibling to copy |
|---|---|---|
| New example resource type | `<name>.yaml` + add to CI examples job + `tests/test_smoke_scenarios.py` shape | `pamMachine.yaml` |
| New scaffold-only family sample | `examples/scaffold_only/<name>.yaml` + CI validate loop already glob-matches `scaffold_only/*.yaml` | `vaultMinimal.yaml` |

## Hard rules

- Each example MUST validate clean WITHOUT `DSK_PREVIEW=1`.
- No `rotation_settings`, `jit_settings`, `gateway.mode: create`, top-level `projects[]` (would need preview gate → ineligible).
- No real secrets. Use placeholder strings; redaction patterns will catch real ones in CI.
- Field set kept minimal — full coverage lives in tests + smoke scenarios.

## Reconciliation

`V1_GA_CHECKLIST.md` §1 — root `examples/*.yaml`: **offline validate + mock plan**
in CI. **`examples/scaffold_only/*.yaml`:** **validate** in the same CI job;
mock **`plan`** for scaffolds is **not** in the `examples` job loop (vault plan
coverage lives in pytest). All shipped examples match schema + preview-gate
contract.

## Note on `examples/invalid/`

The DOR ships an `examples/invalid/*.yaml` corpus. This repo's
`tests/test_schema.py` (W9) auto-discovers them at collection time. Today
that corpus lives in the upstream sibling repo and is mirrored as needed
into `tests/fixtures/examples/`. New invalid fixtures land in `tests/fixtures/`
or upstream — NOT here, because `examples/` must remain "all green" inputs.
