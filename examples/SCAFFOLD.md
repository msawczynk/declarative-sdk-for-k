# `examples/` — canonical minimal manifests

Root `*.yaml` files are validate-clean examples for the packaged declarative
families that have CLI validation paths today: `pam-environment.v1`,
`keeper-vault.v1`, and `keeper-vault-sharing.v1`.

`examples/scaffold_only/*.yaml` remain tiny packaged-family starter documents.
They are kept for backwards-compatible references and schema smoke coverage.
Root examples are validated by the dedicated `examples-validate` CI job with
`python -m keeper_sdk.cli validate`; the existing `examples` CI job also validates
root + scaffold-only manifests and runs mock plans for root examples.

## Files

| File | Resource type | Notes |
|---|---|---|
| `pamMachine.yaml` | `pamMachine` | Reference shape — copy this for new examples. |
| `pam-machine-multi.yaml` | `pamMachine` | Three machines, mixed string/integer ports, and RBI connection options. |
| `pamDatabase.yaml` | `pamDatabase` | Includes `database_type` to satisfy verifier. |
| `pam-database-cluster.yaml` | `pamDatabase` | Primary + replica records sharing one PAM configuration. |
| `pamDirectory.yaml` | `pamDirectory` | Includes directory-specific binding fields. |
| `pamRemoteBrowser.yaml` | `pamRemoteBrowser` | Connection settings only — RBI tri-state and audio keys remain preview-gated. |
| `sharing.example.yaml` | `keeper-vault-sharing.v1` | Minimal folder, shared-folder, record-share, and folder-grantee rows. |
| `sharing-folders-shared.yaml` | `keeper-vault-sharing.v1` | Three folders plus two shared folders. |
| `sharing-grantees.yaml` | `keeper-vault-sharing.v1` | User, team, record, and default share-folder rows. |
| `vault-records.yaml` | `keeper-vault.v1` | Five L1-compatible login records exercising login, payment-card, database, server, and custom field payloads. |
| `vault-record-types.yaml` | `keeper-vault.v1` | Custom `record_types[]` declarations. |
| `vault-attachments.yaml` | `keeper-vault.v1` | `attachments[]` declarations attached to a login record. |

### `scaffold_only/` (packaged families; CI validate)

| File | `schema:` | Notes |
|---|---|---|
| `vaultMinimal.yaml` | `keeper-vault.v1` | Empty `records` — offline `dsk validate` + `dsk validate --json` (`vault_offline`). |
| `vaultOneLogin.yaml` | `keeper-vault.v1` | Single **`login`** row for L1 lab / V8 prep; edit `uid_ref` / titles for your folder. |
| `vaultSharingMinimal.yaml` | `keeper-vault-sharing.v1` | Empty sharing blocks (defaults). |

## Where to land new work

| Change | File | Sibling to copy |
|---|---|---|
| New example resource type | `<name>.yaml` + add to CI examples job + `tests/test_smoke_scenarios.py` shape | `pamMachine.yaml` |
| New vault example | `<name>.yaml` + `tests/test_examples_validate.py` covers schema validation | `vault-records.yaml` |
| New sharing example | `<name>.yaml` + `tests/test_examples_validate.py` covers schema validation | `sharing.example.yaml` |
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
