# Schema body conventions

**Audience:** any agent (worker or parent) about to write or edit a
`<family>.v1.schema.json` file. Read this BEFORE the per-family decision
memo. The memo specifies WHAT the schema covers; this doc specifies HOW
to encode it consistently across families.

**Update rule:** parent-owned. Workers may propose amendments in their
DONE-dump as `LESSON CANDIDATE` rather than editing this file directly.

---

## File layout

Every family lives at:

```
keeper_sdk/core/schemas/<family>/<family>.v<major>.schema.json
```

One JSON file per family per major version. No fragment files, no
helper modules, no per-block separate files. Definitions and references
all live inside the single schema document via `$defs`.

---

## Required top-level fields

Every schema MUST declare:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://keeper.io/sdk/schemas/<family>/<family>.v<major>.schema.json",
  "title": "<family>.v<major>",
  "description": "<one-paragraph description citing the family's V2_DECISIONS Q1 row>",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema"],
  "x-keeper-live-proof": { ... },
  "properties": {
    "schema": { "const": "<family>.v<major>" },
    ...top-level blocks...
  },
  "$defs": { ... }
}
```

`$id` URL is symbolic — not currently fetched at validation time. Pattern
matters more than reachability.

---

## `additionalProperties: false` rule

Every object schema (top-level, nested, in `$defs`) MUST set
`additionalProperties: false`. Exceptions require an inline comment
citing why and a TODO with the slice that should tighten it.

Worker check before commit:

```bash
python -c "
import json, sys
p = sys.argv[1]
def walk(node, path):
    if isinstance(node, dict):
        if node.get('type') == 'object' and 'additionalProperties' not in node and '\$ref' not in node:
            print(f'MISSING additionalProperties at {path}')
        for k, v in node.items():
            walk(v, f'{path}.{k}')
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(v, f'{path}[{i}]')
walk(json.load(open(p)), '\$')
" keeper_sdk/core/schemas/<family>/<family>.v1.schema.json
```

Empty output = clean.

---

## `x-keeper-live-proof` block (mandatory)

Every schema carries this block per `_meta/x-keeper-live-proof.schema.json`:

```json
"x-keeper-live-proof": {
  "status": "scaffold-only",
  "evidence": "memo:<YYYY-MM-DD>_<family>-v<major>-schema-design.md",
  "since_pin": "<full 40-char Commander SHA from .commander-pin>",
  "notes": "<one-line context>"
}
```

`status` enum:

| Value | When |
|---|---|
| `scaffold-only` | Schema body shipped, no live transcript yet (default for fresh impl slices). |
| `preview-gated` | Offline-green; live blocked behind `DSK_PREVIEW=1` env. |
| `supported` | Clean live re-plan transcript exists (cite via `evidence`). |
| `upstream-gap` | Commander itself blocks the surface; cite issue. |
| `dropped-design` | Family considered + rejected; surface ships as runtime verbs. |

`since_pin` is the FULL 40-char SHA, NOT the abbreviated form. Read it
literally from `.commander-pin` (single line, trim whitespace).

`evidence` for `scaffold-only`: cite the design memo. For `supported`:
cite both the memo AND the live transcript path.

---

## Cross-family reference grammar (V2_DECISIONS Q1, frozen)

Cross-family refs use the form:

```
<family>:<key>:<lookup>
```

Where `<lookup>` is a `uid_ref` value (URL-safe base64-ish identifier
the manifest author defined elsewhere in the same or another family).
Schema-level validation of refs uses this regex:

```
^<family>:(<allowed_keys>):[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$
```

Examples:

| Ref | Meaning |
|---|---|
| `keeper-vault:records:db-prod` | Reference a record `db-prod` in the vault family. |
| `keeper-enterprise:teams:platform-eng` | Reference a team `platform-eng` in the enterprise family. |
| `keeper-vault-sharing:folders:archive` | Self-reference within sharing family. |

Define each accepted ref pattern as a separate `$defs` entry:

```json
"$defs": {
  "vault_record_ref": {
    "type": "string",
    "pattern": "^keeper-vault:records:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
  },
  ...
}
```

Then reference via `{"$ref": "#/$defs/vault_record_ref"}` at every use
site. DRY at the schema level.

---

## `uid_ref` semantic uniqueness

JSON Schema CANNOT enforce cross-array `uid_ref` uniqueness within a
single manifest (e.g. `records[].uid_ref` colliding with
`record_types[].uid_ref`). Carry the invariant via the family's test
module:

```python
def test_<family>_schema_rejects_uid_ref_collisions():
    """Cross-block uid_ref uniqueness is enforced semantically; JSON
    Schema's uniqueItems is per-array only."""
    document = {
        "schema": "<family>.v1",
        "block_a": [{"uid_ref": "shared-id", ...}],
        "block_b": [{"uid_ref": "shared-id", ...}],  # collision
    }
    with pytest.raises(SchemaError) as exc:
        _validate(document)
    assert "duplicate uid_ref" in exc.value.reason
    assert "shared-id" in exc.value.reason
```

Add this test for EVERY family with `uid_ref` fields across multiple
top-level blocks. The check belongs in the family's test module, not
in a global validator (each family's collision domain is its own).

---

## Required-field rejection tests

For each top-level block, every `required` field gets a dedicated
test asserting it raises `SchemaError` when missing:

```python
@pytest.mark.parametrize("missing_field", ["uid_ref", "email", ...])
def test_<family>_<block>_rejects_missing_required(missing_field):
    payload = {"uid_ref": "u1", "email": "a@b.c", ...}
    payload.pop(missing_field)
    with pytest.raises(SchemaError):
        _validate({"schema": "<family>.v1", "<block>": [payload]})
```

---

## File-formatting protocol

**Do NOT run `ruff format` over the schemas directory.** It introduces
JSONC trailing commas that break strict JSON parsers. The CI workflow
runs `python -m json.tool` against every schema file as a guard
(see `schema-validate` job in `.github/workflows/ci.yml`).

If your editor auto-formats on save:

1. Configure it to skip `*.schema.json` under this directory, OR
2. After save, run:

   ```bash
   python -m json.tool < <path> > /dev/null
   ```

   to verify validity. Fix any error before commit.

---

## Future-slice TODO marker

When a slice ships scaffold-stubs for blocks that fully populate in a
LATER slice, leave a top-level comment block (JSON has no comments;
use a `$comment` field on the relevant `$defs` entry):

```json
"$defs": {
  "node_stub": {
    "$comment": "TODO: populate the scaffolded node fields before promoting this block (parent_node_uid_ref, name, type enum, restrict_visibility flag).",
    "type": "object",
    "additionalProperties": false
  }
}
```

The `$comment` keyword is JSON Schema 2020-12 native and allowed by
`additionalProperties: false` parents because it's at the meta-keyword
level. Consumers MAY ignore it; tooling MUST NOT reject it.

---

## Test module style (canonical sibling: `test_keeper_vault_sharing_schema.py`)

Read that file before authoring a new family's test module. Match its:

- Import block (one import per line, alphabetized).
- `_validate()` helper (same shape across families).
- Per-block test grouping (use class-based grouping for blocks with >5
  test cases, function-based for smaller blocks).
- Sample-manifest fixtures defined as string literals inside test
  functions, NOT under `tests/fixtures/`. Smaller blast radius +
  test-local context.

---

## Commit message convention

Schema body slices use:

```
feat(schema): <family>.v<major> body — <slice scope>
```

Where `<slice scope>` lists the top-level blocks fully populated. Stub
blocks not mentioned. Body line cites the memo:

```
memo: 2026-04-26_<family>-v<major>-schema-design.md
```

---

## When to amend this doc

Amend when a new family surfaces a pattern that the existing
conventions don't cover. Workers propose amendments as `LESSON
CANDIDATE` in their DONE-dump; parent integrates after 2+ families
hit the same pattern. Don't amend on a single-family quirk.
