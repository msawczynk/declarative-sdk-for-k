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

Use `--provider commander` (with `KEEPER_DECLARATIVE_FOLDER` set) to delegate
to the installed `keeper` CLI via subprocess. Deletion via the Commander
provider is intentionally unsupported for v1; operators must remove records
manually or stay on the mock/core path.

## Exit codes

| code | meaning                    |
|------|----------------------------|
| 0    | success / clean plan       |
| 1    | unexpected error           |
| 2    | schema validation error    |
| 3    | uid_ref / graph / cycle    |
| 4    | plan has conflicts         |
| 5    | capability / provider fail |

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

## Testing

```bash
pytest
```

42 tests cover: manifest load/dump, schema validation (happy + 7 invalid
fixtures), semantic rules, graph + topological order + cycle detection,
change classification (create / update / delete / noop / conflict /
adoption), ownership metadata round-trip, redaction, planner ordering,
MockProvider two-phase apply, and CLI smoke tests.

## Relationship to `keeper-pam-declarative/`

The sibling package is the **design of record**: schema, documentation,
invalid fixtures, architecture, and delivery plan. This SDK implements that
design. When the contract changes, update the sibling first, then re-copy
`manifests/pam-environment.v1.schema.json` into
`keeper_sdk/core/schemas/pam-environment.v1.schema.json`.
