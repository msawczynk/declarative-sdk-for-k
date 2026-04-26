# Next sprint — heavy parallel orchestration plan

**Purpose:** Run **most** work concurrently while keeping **merge order**, **live-tenant serialization**, and **CI truth** intact. This doc is the parent’s flight checklist; workers get **only** their package + “do not touch” list.

**Authority:** When this conflicts with a wish-list roadmap, [`SDK_DA_COMPLETION_PLAN.md`](./SDK_DA_COMPLETION_PLAN.md) and [`SDK_ORCHESTRATED_FEATURE_COMPLETE.md`](./SDK_ORCHESTRATED_FEATURE_COMPLETE.md) win on support claims.

---

## 1. Sprint outcome (one sentence)

**Graduate vault + vault-sharing toward live-proof-ready** *or* document blockers; **land P18 decision memo**; **advance P11** with ≥2 non-overlapping schema slices in parallel; **optional** fourth `dsk report` verb **only** if a memo lands first — all without serializing unrelated readonly work.

---

## 2. Dependency graph (what can actually run in parallel)

```text
                    ┌─────────────────────┐
                    │  W0: Parent branch  │
                    │  (integration only) │
                    └──────────┬──────────┘
           ┌───────────────────┼───────────────────┐
           ▼                   ▼                   ▼
   ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
   │ R1: P18 memo  │   │ R2: P11 slice │   │ R3: Report    │
   │ (readonly)    │   │ memos (ro)    │   │ argv memo (ro)│
   └───────┬───────┘   └───────┬───────┘   └───────┬───────┘
           │                   │                   │
           ▼                   ▼                   ▼
   ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
   │ F1: P18 impl  │   │ F2: P11 JSON  │   │ F4: report    │
   │ (after R1)    │   │ (2 workers)   │   │ (after R3)    │
   └───────────────┘   └───────────────┘   └───────────────┘

   ┌───────────────┐         ┌────────────────────────────┐
   │ R4: Live-proof│         │ L1: Parent live smoke     │
   │ prep (ro)     │────────▶│ (serial per tenant)      │
   └───────────────┘         └─────────────┬──────────────┘
                                           ▼
                               ┌───────────────────────┐
                               │ F3: evidence + schema │
                               │ pointer edits         │
                               └───────────────────────┘
```

**Hard serializations (do not parallelize these):**

| Resource | Rule |
|----------|------|
| **Lab tenant / Commander session** | One parent (or one smoke runner) at a time; workers **never** hold the live gate. |
| **`main` integration** | One parent merges fan-in files per wave (see §5). |
| **P18 code** | Starts only after **R1** memo is merged or explicitly accepted in-thread. |
| **New `dsk report` verb** | Starts only after **R3** memo; conflicts on `keeper_sdk/cli/main.py` — one worker or strict file ownership. |

**Soft parallelizations (high leverage):**

| Track | Parallelism |
|-------|-------------|
| **Readonly memos** | R1, R2, R3, R4 can all run **same day** on different workers; zero merge conflicts if outputs go to `_memos/` or chat only. |
| **P11 schema bodies** | F2 splits by **file**: e.g. worker A touches only `enforcements` / `$defs`; worker B only `aliases`; parent resolves `$ref` cross-links in a single integration commit if needed. |
| **Live-proof prep** | R4: checklist, directory layout, sanitization recipe, `x-keeper-live-proof` draft text — **no** tenant. |
| **Tests** | Each F* worker adds tests colocated with their feature path; parent runs full `pytest` once per merge wave. |

---

## 3. Work packages (assignable units)

Each package has: **ID**, **type** (`R` = readonly memo, `F` = foreground impl), **touch paths**, **deps**, **parallel group** (`G1` = wave 1 same-day parallel, `G2` = after deps).

### Readonly / design (G1 — dispatch together)

| ID | Deliverable | Worker output | Deps |
|----|-------------|---------------|------|
| **R1** | P18 extractor scope memo: which Commander entrypoints, nested `GroupCommand` rules, snapshot schema shape, `--check` behavior, risk list | `LESSON CANDIDATE` + `JOURNAL CANDIDATE` + file under operator `_memos/` if used | None |
| **R2a** | P11 next slice: `enforcements` (or chosen slice) — Commander argv + readback shape + `$ref` needs | Memo only | CONVENTIONS.md |
| **R2b** | P11 next slice: `aliases` / `enterprise_pushes` / richer `nodes` — **disjoint** from R2a | Memo only | CONVENTIONS.md |
| **R3** | Optional 4th report verb: exact Commander argv, JSON shape sample, redaction story, leak-check edge cases | Memo only | AGENTS.md report table |
| **R4** | Live-proof runbook: steps, evidence filename convention, grep allowlist, what **must not** appear in artifact | Memo + optional checklist in `docs/live-proof/README.md` **if** parent approves doc add | LOGIN.md / smoke README |

### Foreground impl (G2 — parallel where paths disjoint)

| ID | Deliverable | Touch paths (typical) | Deps |
|----|-------------|------------------------|------|
| **F1** | P18: extend `scripts/sync_upstream.py` + regenerate snapshot **or** stub registry behind feature flag per R1 | `scripts/sync_upstream.py`, `docs/capability-snapshot.json`, `docs/CAPABILITY_MATRIX.md`, CI drift job | R1 accepted |
| **F2a** | P11 schema: slice from R2a | `keeper_sdk/core/schemas/keeper-enterprise/*.json`, `tests/test_keeper_enterprise_schema.py` | R2a |
| **F2b** | P11 schema: slice from R2b | same family **different** `$defs` blocks / sections agreed in memo | R2b |
| **F3** | Live-proof: sanitized artifact + schema `x-keeper-live-proof` + test if any | `docs/live-proof/*`, schema JSON, maybe `tests/test_*_schema.py` | L1 complete |
| **F4** | Fourth report verb per R3 | `keeper_sdk/cli/_report/*.py`, `main.py`, `tests/test_cli.py` | R3 |

### Explicit non-goals this sprint (prevents scope creep)

- No **gate lift** from `preview-gated` to `supported` without SDK_DA §Completion Gates.
- No **P13.5 bus** implementation unless a product decision memo closes it — at most a **one-pager defer** in R1’s backlog section.

---

## 4. Parallel waves (timeline-shaped, not calendar)

### Wave 0 — same session, parent (≤30 min)

1. Create **integration branch** `sprint/parallel-<date>` from `main` **or** use `main` with strict “merge train” order.
2. Post **WORK PACKAGE TABLE** (§3) to orchestration channel with worker IDs.
3. Pin **CONVENTIONS.md** + `docs/V2_DECISIONS.md` Q1 row in every worker preamble.

### Wave 1 — readonly burst (wall clock ~10–20 min with 4 workers)

Launch **R1, R2a, R2b, R4** in parallel (add **R3** only if report expansion is in scope).

**Worker preamble (copy-paste):**

```text
Read first: keeper_sdk/core/schemas/CONVENTIONS.md, docs/V2_DECISIONS.md (Q1 only).
Do NOT edit: JOURNAL.md, LESSONS.md, .github/workflows/* (unless task says).
Output: memo body + DONE dump with LESSON CANDIDATE / JOURNAL CANDIDATE if needed.
No keeper login; no fetch; evidence is paths + reasoning only.
```

### Wave 2 — parent triage (≤45 min)

1. Resolve contradictions between R2a / R2b memos (one owner decision).
2. Accept / revise R1 → unlock F1.
3. Accept R4 → schedule L1 on lab calendar.

### Wave 3 — implementation burst (max parallel = disjoint paths)

| Slot | Worker | Condition |
|------|--------|-----------|
| 1 | F2a | R2a accepted |
| 2 | F2b | R2b accepted and **file-level** disjoint from F2a |
| 3 | F1 | R1 accepted; **isolate** to script + generated docs |
| 4 | F4 | R3 accepted **and** `main.py` not being edited by F2* |

If **F4** and **F2a** both need `main.py`, **sequence** them (F2 first or F4 first — pick by blast radius: usually schema first).

### Wave 4 — live gate (serial)

1. **L1:** Parent runs whitelisted smoke / live steps from R4 runbook; captures raw transcript **only** to secure scratch; produces sanitized artifact.
2. **F3:** Worker or parent applies schema pointer + doc links + optional test assertions on **paths only** (no secret values in repo).

### Wave 5 — integration

1. Single parent merge train: `F2a` + `F2b` → resolve JSON `$ref` if both touched same file → **one** integration commit if same file.
2. `F1` separately if drift CI is noisy (own PR acceptable).
3. `F3` last or with F2 — depends on whether schemas reference new proof paths.

---

## 5. Merge fan-in map (conflict avoidance)

| Hot file | Policy |
|----------|--------|
| `keeper_sdk/cli/main.py` | **One** assignee per wave; report verbs and unrelated CLI flags do not share a wave with other `main.py` edits. |
| `keeper_sdk/core/schemas/keeper-enterprise/keeper-enterprise.v1.schema.json` | Prefer **one worker per slice** on **different `$defs` keys**; if both must touch same file, **do not** parallelize — use sequential workers or one worker two slices. |
| `docs/capability-snapshot.json` | **F1 only** in that wave; no other worker edits. |
| `.github/workflows/ci.yml` | Parent only unless dedicated CI worker owns the whole file. |

---

## 6. CI / quality gates per merge wave

Minimum before each push to integration branch:

```bash
python3 -m pytest -q
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy keeper_sdk
```

If **F1** or any `**/*.json` schema change:

```bash
python3 scripts/sync_upstream.py --check   # when capability surface touched
python3 -m json.tool keeper_sdk/core/schemas/.../*.json >/dev/null  # strict JSON
```

Parent runs **full** pre-merge pass once per train before `main` merge per [`SDK_ORCHESTRATED_FEATURE_COMPLETE.md`](./SDK_ORCHESTRATED_FEATURE_COMPLETE.md).

---

## 7. DONE contract (worker → parent)

Each worker ends with:

1. **Files touched** (list).
2. **Commands run** (pytest subset ok for workers; parent runs full).
3. **SUPPORT CLAIM CHECK:** one line — “no new supported claims” / “docs updated in …”.
4. **DRIFT ANNOTATIONS:** any `path:line` staleness found in parent task body (LESSON pattern from daybook).
5. **BLOCKERS:** tenant, upstream Commander, or design ambiguity — stop, do not guess.

---

## 8. Daybook alignment

- **Workers:** read Downloads `JOURNAL.md` / `LESSONS.md` silently; **no** edits unless task whitelists them.
- **Parent:** append one sprint block + rollup test count; run `sync_daybook.sh` after `JOURNAL`/`LESSONS` edits.
- **Distillation:** if sprint tail > ~2 screens, collapse older SDK sprints into one “burst” summary (per daybook skill).

---

## 9. Risk register (parallel-specific)

| Risk | Mitigation |
|------|------------|
| Duplicate work on same `$def` | R2a/R2b memos name **exact JSON pointers** they own. |
| Drift between memos and code | Parent runs devil-check: “does board match `pytest` count?” |
| JSONC / trailing comma in schemas | CI strict JSON guard; workers run `python3 -m json.tool` on touched schemas. |
| Live proof leaks | R4 runbook + existing `secret_leak_check` pattern; re-grep artifact in CI if added. |
| Worktree `.git` file breaks scripts | Use lessons from daybook: porcelain path parsing, not `$N` awk fields. |

---

## 10. Success criteria (sprint exit)

At least **three** of:

1. **F3** or documented **blocker** for vault / vault-sharing live-proof (honest status).
2. **R1** merged or filed + **F1** started or PR open.
3. **F2a** or **F2b** merged to `main` (or integration branch with green CI).
4. **R4** runbook exists and **L1** scheduled or executed.
5. **R3** explicitly **deferred** with one-line reason (valid outcome).

---

## 11. Quick-launch checklist (parent)

- [ ] Branch / merge train strategy chosen  
- [ ] Wave 1 workers launched (R1, R2a, R2b, R4 [+ R3])  
- [ ] Wave 2 triage complete; F* unlocked  
- [ ] Hot files assigned exclusively  
- [ ] Live tenant slot reserved for L1 only  
- [ ] Final integration: full pytest + ruff + mypy + (drift if touched)  
- [ ] `CHANGELOG.md` / `AGENTS.md` if user-visible CLI or support text changed  
- [ ] Daybook rollup line updated  

This plan is safe to attach to Codex / Cursor worker prompts as the **orchestration index**; slice-specific bodies stay in per-task prompts.
