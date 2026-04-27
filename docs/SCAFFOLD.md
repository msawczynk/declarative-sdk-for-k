# `docs/` — operator + agent docs

Focused, machine-parseable where possible. No tutorials. Each doc owns one
contract.

## Files

| File | Audience | Owns |
|---|---|---|
| `COMMANDER.md` | maintainer / operator | Pinned Commander SHA + capability matrix + post-import tuning field map (P3.1 readback bucket vocab — `import-supported`/`edit-supported-clean`/`edit-supported-dirty`/`upstream-gap`). Drift policy. |
| `CAPABILITY_MATRIX.md` | maintainer / agent | Generated mirror of upstream Commander capabilities. Consumed by CI `drift-check`. |
| `capability-snapshot.json` | machine | Machine-readable mirror; `scripts/sync_upstream.py --check` diff-checks against upstream. |
| `LOGIN.md` | operator | `EnvLoginHelper` contract + 30-line custom-helper skeleton. |
| `VALIDATION_STAGES.md` | agent / CI | Per-stage `validate --online` contract; which exit code fires for which failure. Disambiguates exit-2 overload. **`keeper-vault.v1` L1:** operator caveats (semantic diff limits, races, offline vs `vault_online` CI) in section *Vault — operator caveats*. |
| `VAULT_L1_DESIGN.md` | integrator / agent | Vault slice-1 scope, markers, discover mapping; **§4** semantic `login` diff limits, concurrent edits, Commander UPDATE notes. **§7** sign-off clears ledger G2. |
| `live-proof/README.md` | operator / integrator | Sanitized transcript naming, redaction bar, L1 checklist, **V8 prep** template pointer; `keeper-vault.v1.sanitized.template.json` (shape-only, `template: true`). CI `schema-validate` runs `json.tool` on `docs/live-proof/*.json`. |
| `SDK_DA_COMPLETION_PLAN.md` | maintainer | **Devil's-advocate** completion gates. `supported`/`preview-gated`/`upstream-gap`. Wins over wish-list roadmaps. |
| `SDK_COMPLETION_PLAN.md` | maintainer | Long-form roadmap + risk gates (companion to DA plan). |
| `DSK_NEXT_WORK.md` | maintainer / agent | In-repo **product** priority queue (live gates, `phase_harness`, pointers). Not daybook. |
| `RELEASING.md` | maintainer | Release ritual. **GitHub-only**, no PyPI. |
| `ISSUE_6_JIT_SUPPORT_BOUNDARY.md` | maintainer | JIT apply boundary against pinned Commander; no safe writer → `upstream-gap`. |
| `ISSUE_7_GATEWAY_CREATE_PROJECTS_DESIGN.md` | maintainer | Gateway `mode: create` + top-level `projects[]` design boundary. |

## Where to land new work

| Change | File | Sibling to copy |
|---|---|---|
| New CLI exit code / stage | `VALIDATION_STAGES.md` + `AGENTS.md` exit-code table | existing stage row |
| Vault L1 semantics / caveats | `VAULT_L1_DESIGN.md` §4 + `VALIDATION_STAGES.md` (vault section) + `AGENTS.md` (validate pointer + playbook **§E** programmatic loaders) | §4 revision row |
| New Commander surface used | `COMMANDER.md` capability table | existing row |
| New phase or gate | `SDK_DA_COMPLETION_PLAN.md` + `SDK_COMPLETION_PLAN.md` | P3 row |
| New design boundary doc | `ISSUE_<n>_<topic>.md` | `ISSUE_6_JIT_SUPPORT_BOUNDARY.md` |
| New login flow | `LOGIN.md` | helper-skeleton block |
| New release knob | `RELEASING.md` | publish-workflow row |
| Live-proof / `x-keeper-live-proof` | `live-proof/README.md` + family schema block | `CONVENTIONS.md` + `_meta/x-keeper-live-proof.schema.json` |
| CI `examples` job vs pytest (vault mock plan) | [`examples/SCAFFOLD.md`](../examples/SCAFFOLD.md) | existing examples row |

## Hard rules

- Tables stable column-order — agents parse them.
- Capability claims MUST include classification (`supported`/`preview-gated`/`upstream-gap`).
- No tutorials. No screenshots. No marketing copy.
- DOR (`keeper-pam-declarative/`) is the upstream design source — link, don't copy.
- `CHANGELOG.md` lives at root (Keep-a-Changelog format), not here.

## Reconciliation status

All 7 DOR contradictions raised + resolved (D-5; see `AUDIT.md` 2026-04-24
"finish-it-all"). DOR reframed from "spec to implement" to "capability mirror"
post-2026-04-24 (`V1_GA_CHECKLIST.md` § 2). No open doc-vs-code drift.
