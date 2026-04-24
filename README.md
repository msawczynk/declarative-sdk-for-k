# keeper-declarative-sdk

Reference implementation of the Keeper PAM declarative design shipped in
[`keeper-pam-declarative/`](../keeper-pam-declarative/). Pure Python, no
Commander imports, no network I/O in the core.

```
keeper_sdk/
  core/           # pure models, schema, graph, diff, planner, metadata, redact
    schemas/      # packaged pam-environment.v1.schema.json
  providers/      # MockProvider, CommanderCliProvider (subprocess-backed)
  cli/            # `keeper-sdk` (validate / export / plan / diff / apply)
tests/            # pytest suite; reuses the authoritative fixtures in
                  # ../keeper-pam-declarative/examples
```

## Install

```bash
pip install -e '.[dev]'
```

Requires Python 3.10+. `jsonschema` is used when available; the core falls
back to typed-model validation when it isn't.

## Quick start

```bash
# 1. validate (schema + typed models + semantic rules)
keeper-sdk validate ../keeper-pam-declarative/examples/minimal/environment.yaml

# 2. plan against the MockProvider (deterministic, in-memory)
keeper-sdk plan ../keeper-pam-declarative/examples/minimal/environment.yaml

# 3. apply (dry-run-first-friendly, idempotent; second apply is clean)
keeper-sdk apply ../keeper-pam-declarative/examples/minimal/environment.yaml --auto-approve

# 4. lift a Commander export into a manifest
keeper-sdk export path/to/pam-project-export.json --output env.yaml
```

## Status (sdk-completion branch, as of 2026-04-24)

Core + mock: complete.
Commander CLI provider: partial — discover, apply (import/extend), and
capability checks are wired; delete support and per-record metadata
writeback are on the sdk-completion roadmap (Phase C: W13–W18).

Use `--provider commander` (with `KEEPER_DECLARATIVE_FOLDER` set) to delegate
to the installed `keeper` CLI via subprocess. Deletion via the Commander
provider is intentionally unsupported for v1; operators must remove records
manually or stay on the mock/core path.

## Exit codes

| code | command    | meaning                    |
|------|------------|----------------------------|
| 0    | plan/diff  | clean plan                 |
| 0    | apply      | applied successfully       |
| 0    | validate   | manifest ok                |
| 1    | any        | unexpected error           |
| 2    | plan/diff  | changes present            |
| 2    | validate   | schema failure             |
| 3    | any        | uid_ref / graph / cycle    |
| 4    | plan/diff  | conflicts present          |
| 4    | apply      | conflicts refused apply    |
| 5    | any        | capability / provider fail |

## Programmatic use

```python
from keeper_sdk.core import (
    load_manifest, build_graph, execution_order,
    compute_diff, build_plan,
)
from keeper_sdk.providers import MockProvider

manifest = load_manifest("env.yaml")
provider = MockProvider(manifest.name)

graph = build_graph(manifest)
order = execution_order(graph)
changes = compute_diff(manifest, provider.discover())
plan = build_plan(manifest.name, changes, order)
provider.apply_plan(plan)
```

`compute_diff` has a keyword-only `adopt=False` flag. Unmanaged live records
that match a manifest resource by title surface as `CONFLICT` by default; pass
`adopt=True` (or the future `keeper-sdk import` subcommand, per W18) to write
ownership markers over them.

## Testing

```bash
pytest
```

58 tests now cover manifest load/dump, canonicalisation, pam_import
round-trip, and schema validation across 7 parametrised invalid fixtures,
including cyclic refs. They also cover semantic rules (gateway-create, RBI
rotation/JIT, rotation on non-rotatable resources, and the
`pam_configuration` requirement), graph build across shared folders and
projects with topological order and cycle detection, diff taxonomy
(create/update/delete/noop/conflict/collision plus adoption opt-in),
MockProvider two-phase apply, Renderer protocol conformance, and a 500-resource
performance smoke.

CLI smokes exercise `validate`, `export`, `plan` exit codes (`0`/`2`/`4`),
`apply --dry-run` equivalence to `plan`, and JSON output.

## Relationship to `keeper-pam-declarative/`

The sibling package is the **design of record**: schema, documentation,
invalid fixtures, architecture, and delivery plan. This SDK implements that
design. When the contract changes, update the sibling first, then re-copy
the schema and marker contract (including `MANAGER_NAME =
"keeper-pam-declarative"`), then re-copy
`manifests/pam-environment.v1.schema.json` into
`keeper_sdk/core/schemas/pam-environment.v1.schema.json`.
