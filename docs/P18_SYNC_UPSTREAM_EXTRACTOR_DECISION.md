# P18 — `sync_upstream.py` extractor expansion (decision memo, R1)

**Status:** **P18a + P18b landed** in `scripts/sync_upstream.py` (enterprise +
vault/integrations registry + matrix sections). **P18c** (optional JSON
allowlist helper) remains open. **Authority:** `docs/V2_DECISIONS.md` (P18), `docs/NEXT_SPRINT_PARALLEL_ORCHESTRATION.md` §15.1–15.2.

## 1. Current state (fact)

`scripts/sync_upstream.py` today imports a **fixed** tuple of Commander
classes:

- **`_GROUPS`:** `PAMProjectCommand`, `PAMRbiCommand`, plus **P18b** `ScimCommand`,
  `AutomatorCommand`, `TrashCommand`
- **`_COMMAND_CLASSES`:** PAM import/extend/rbi-edit/connection-edit **plus**
  six enterprise commands (`GetEnterpriseDataCommand`, `EnterpriseInfoCommand`,
  …) — P18a
- **`extract_enforcements`:** filtered `keepercommander.constants` rows
- **`parse_readme_shapes`:** `pam_import/README.md` for resource-type JSON hints

Output: `docs/CAPABILITY_MATRIX.md` + `docs/capability-snapshot.json`. CI runs
`--check` against the committed snapshot at `.commander-pin`.

## 2. Goal (P18)

Machine-readable coverage **beyond PAM** for every family the SDK claims to
model — without hand-maintaining a second registry that drifts from Commander.

Full “137 roots” enumeration is **not** required for the first merge; the goal
is a **repeatable registration pattern** + enough new rows to cover **gap-closure
sprint** priorities (enterprise, vault-adjacent surfaces, etc.).

## 3. Non-goals (first implementation slice)

- Replacing Commander’s own CLI docs for end users (still **upstream** support
  text).
- Dynamic `import *` or runtime `pkgutil.walk_packages` without an allowlist
  (security + determinism).
- Changing snapshot **consumer** contracts in `keeper_sdk` until JSON schema for
  `capability-snapshot.json` is versioned (optional follow-up).

## 4. Design decisions (recommended)

### D1 — Registration model

**Chosen approach:** extend `_GROUPS` / `_COMMAND_CLASSES` (or a single
`_REGISTRY: tuple[RegistryEntry, ...]`) with **explicit** `(module, attr,
display_label)` entries per new surface. Each PR adds rows for the families it
touches.

**Rejected for v1 of P18:** blind walk of `keepercommander.commands` — too
noisy, breaks CI when Commander refactors package layout.

### D2 — Nested `GroupCommand`

Use existing `extract_group_subcommands(cls)` for each registered group.
Nested groups (sub-menus) appear as additional **group** rows with dotted
labels, e.g. `enterprise user` — document naming in matrix header comment.

### D3 — Snapshot stability

- Keep `commander_sha` aligned with `.commander-pin` (40-char in schema
  annotations; short in matrix title per existing script).
- Continue stripping environment-dependent fields from `--check` comparison if
  CI adds noise (see daybook LESSON on `commander_branch` drift).

### D4 — CI / checkout

Sibling checkout path stays `../Commander` default; CI already clones at pin.
Adding many imports increases **import-time** failures — each new registry row
must be covered by `sync_upstream.py --check` in CI so missing classes fail
the PR, not production.

### D5 — Phasing (concrete)

| Phase | Scope | Exit |
|-------|--------|------|
| **P18a** | Add 3–5 **enterprise**-related `GroupCommand` / command classes that `keeper-enterprise.v1` references in memos | **Done:** six `Enterprise*` / `GetEnterpriseDataCommand` rows + `## Enterprise commands (extracted, P18a)` in matrix |
| **P18b** | Vault / sharing / integrations command roots used by V2 families | **Done:** `scim` + `automator` + `trash` groups; flags for `get`, `search`, `record-add`, `record-update`, `list-sf`, `ls`; matrix sections **Integrations** + **Vault/trash** + **Vault/folder CLI flags** |
| **P18c** | Optional generic helper that **reads** a static JSON allowlist file in-repo (`scripts/upstream_command_allowlist.json`) so non-Python owners can propose rows | Still explicit; no runtime crawl |

Stop between phases if `--check` diff becomes unreviewable.

## 5. Risks

| Risk | Mitigation |
|------|------------|
| Commander private constructor side effects on import | Import only `GroupCommand` / argparse classes; no `main()` |
| Snapshot merge conflicts | One F1 train owner per pin bump |
| Matrix unreadable | Subsections per product area + TOC in markdown renderer |

## 6. Acceptance (F1 PR)

- `python3 scripts/sync_upstream.py` (regenerate) + `--check` green.
- `docs/CAPABILITY_MATRIX.md` shows new sections with Commander class citations.
- No change to SDK_DA support claims unless paired with proof elsewhere.

## 7. References

- `scripts/sync_upstream.py` — `_GROUPS`, `_COMMAND_CLASSES`, `build_snapshot`
- `.commander-pin`
- `docs/NEXT_SPRINT_PARALLEL_ORCHESTRATION.md` §15.2 track **B**
