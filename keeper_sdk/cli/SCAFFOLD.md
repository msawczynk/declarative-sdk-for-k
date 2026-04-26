# `keeper_sdk/cli/` — `dsk` entrypoint

Click-based CLI. Owns the exit-code contract (`docs/VALIDATION_STAGES.md`,
`AGENTS.md` exit-code table). Aliases: `pamform`, `keeper-sdk` (removed in v2.0).

## Modules

| File | LOC | Role |
|---|---:|---|
| `__init__.py` | 5 | Package marker. |
| `__main__.py` | 6 | `python -m keeper_sdk.cli` shim → `main:cli`. |
| `main.py` | 469 | Click commands (`validate`, `plan`, `diff`, `apply`, `import`, `export`) + exit-code orchestration. `EXIT_CHANGES == EXIT_SCHEMA == 2` (intentional overload — see comment + DOR). |
| `renderer.py` | 104 | `RichRenderer` — human tables for plan/outcomes/diff. Snapshot-tested in `tests/test_renderer_snapshots.py`. |

## Commands

| Verb | Exit codes | Machine flag | JSON contract |
|---|---|---|---|
| `validate` | 0/2/3/5 | `--emit-canonical` | – |
| `plan` | 0/2/3/4 | `--json` | shape in `AGENTS.md` |
| `diff` | 0/2/3 | – | – |
| `apply` | 0/1/3/4/5 | `--dry-run` (= plan) | per-row outcomes |
| `import` | 0/1/3 | `--dry-run` | adoption plan |
| `export` | 0/1 | `-o FILE` | manifest YAML |
| `bootstrap-ksm` | 0/5/1 | final JSON line | app/record UID prefixes, config path, status |

Every mutating command honours `--auto-approve` and `--allow-delete`.

## Where to land new work

| Change | File | Sibling to copy |
|---|---|---|
| New verb | `main.py` | `import` command block |
| New flag | `main.py` (Click decorator) | `--allow-delete` on `apply` |
| New renderer view | `renderer.py` + `tests/test_renderer_snapshots.py` | `render_diff` |
| New stage in `validate` | `main.py` (`validate` cmd) + `docs/VALIDATION_STAGES.md` + `tests/test_stage_5_bindings.py` | stage-5 path |

KSM bootstrap operator docs live in `docs/KSM_BOOTSTRAP.md`; the command path is
implemented in `main.py` and delegates tenant mutation to
`keeper_sdk/secrets/bootstrap.py`.

## Hard rules

- Exit codes are a binding contract — no renumbering without spec update + CI guard.
- `apply --dry-run` MUST be byte-identical to `plan` (W3 reconciliation; covered by `tests/test_cli.py`).
- All user-visible secrets routed through `core.redact.redact()`.
- No direct provider imports — instantiate via `--provider {mock,commander}` selector pattern.

## Reconciliation vs DOR

- `DELIVERY_PLAN.md` L92 exit-code semantics: matched.
- `keeper-sdk` and `pamform` aliases: shipped, deprecation noted in `AGENTS.md`.
- `validate --online` stages 4 + 5: shipped (W17, then `Provider.check_tenant_bindings()`).
