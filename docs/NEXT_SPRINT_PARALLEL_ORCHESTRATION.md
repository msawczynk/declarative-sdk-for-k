# Next sprint — heavy parallel orchestration plan

**Purpose:** Run **most** work concurrently while keeping **merge order**, **one live writer per tenant at a time**, and **CI truth** intact. This doc is the **integrator’s** flight checklist (human parent or lead agent); every worker gets **only** their package + “do not touch” list.

**Live access:** Maintainers may grant **code** (workers, CI, autonomous agents) the same live-tenant and live-proof responsibilities as a human — see [`AGENTS.md`](../AGENTS.md) § Autonomous execution and [`docs/live-proof/README.md`](./live-proof/README.md). Serialization is **per tenant session**, not “parents only.”

**Authority:** When this conflicts with a wish-list roadmap, [`SDK_DA_COMPLETION_PLAN.md`](./SDK_DA_COMPLETION_PLAN.md) and [`SDK_ORCHESTRATED_FEATURE_COMPLETE.md`](./SDK_ORCHESTRATED_FEATURE_COMPLETE.md) win on support claims.

---

## 1. Sprint outcome (one sentence)

**Graduate vault + vault-sharing toward live-proof-ready** *or* document blockers; **land P18 decision memo**; **advance P11** with ≥2 non-overlapping schema slices in parallel; **optional** fourth `dsk report` verb **only** if a memo lands first — all without serializing unrelated readonly work.

---

## 2. Dependency graph (what can actually run in parallel)

```text
                    ┌─────────────────────┐
                    │  W0: Integrator branch │
                    │  (merge train owner)   │
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
   │ R4: Live-proof│         │ L1: Live smoke / proof    │
   │ prep (ro)     │────────▶│ (1 actor / tenant)       │
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
| **Lab tenant / Commander session** | **One concurrent live actor per tenant** (human, CI job, or explicitly granted agent). Same harness + sanitization rules as `AGENTS.md`; no parallel uncoordinated writers against the same tenant. |
| **`main` integration** | One **integrator** merges fan-in files per wave (see §5); may be human or lead agent. |
| **P18 code** | Starts only after **R1** memo is merged or explicitly accepted in-thread. |
| **New `dsk report` verb** | Starts only after **R3** memo; conflicts on `keeper_sdk/cli/main.py` — one worker or strict file ownership. |

**Soft parallelizations (high leverage):**

| Track | Parallelism |
|-------|-------------|
| **Readonly memos** | R1, R2, R3, R4 can all run **same day** on different workers; zero merge conflicts if outputs go to `_memos/` or chat only. |
| **P11 schema bodies** | F2 splits by **file**: e.g. worker A touches only `enforcements` / `$defs`; worker B only `aliases`; integrator resolves `$ref` cross-links in a single integration commit if needed. |
| **Live-proof prep** | R4: checklist, directory layout, sanitization recipe, `x-keeper-live-proof` draft text — **no** tenant. |
| **Tests** | Each F* worker adds tests colocated with their feature path; integrator runs full `pytest` once per merge wave. |

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
| **R4** | Live-proof runbook: steps, evidence filename convention, grep allowlist, what **must not** appear in artifact | Memo + optional checklist in `docs/live-proof/README.md` **if** maintainer approves doc add | LOGIN.md / smoke README |

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

### Wave 0 — same session, integrator (≤30 min)

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
Unless this task explicitly grants live tenant access: no keeper login; no fetch; evidence is paths + reasoning only.
```

### Wave 2 — integrator triage (≤45 min)

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

1. **L1:** Granted actor (human **or** code: smoke harness, CI workflow, autonomous agent per `AGENTS.md`) runs whitelisted steps from R4 runbook; captures raw transcript **only** to secure scratch; produces sanitized artifact.
2. **F3:** Any assignee applies schema pointer + doc links + optional test assertions on **paths only** (no secret values in repo).

### Wave 5 — integration

1. Single integrator merge train: `F2a` + `F2b` → resolve JSON `$ref` if both touched same file → **one** integration commit if same file.
2. `F1` separately if drift CI is noisy (own PR acceptable).
3. `F3` last or with F2 — depends on whether schemas reference new proof paths.

---

## 5. Merge fan-in map (conflict avoidance)

| Hot file | Policy |
|----------|--------|
| `keeper_sdk/cli/main.py` | **One** assignee per wave; report verbs and unrelated CLI flags do not share a wave with other `main.py` edits. |
| `keeper_sdk/core/schemas/keeper-enterprise/keeper-enterprise.v1.schema.json` | Prefer **one worker per slice** on **different `$defs` keys**; if both must touch same file, **do not** parallelize — use sequential workers or one worker two slices. |
| `docs/capability-snapshot.json` | **F1 only** in that wave; no other worker edits. |
| `.github/workflows/ci.yml` | Integrator only unless a dedicated CI/agent worker owns the whole file end-to-end. |

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

Integrator runs **full** pre-merge pass once per train before `main` merge per [`SDK_ORCHESTRATED_FEATURE_COMPLETE.md`](./SDK_ORCHESTRATED_FEATURE_COMPLETE.md).

---

## 7. DONE contract (worker → integrator)

Each worker ends with:

1. **Files touched** (list).
2. **Commands run** (pytest subset ok for workers; integrator runs full).
3. **SUPPORT CLAIM CHECK:** one line — “no new supported claims” / “docs updated in …”.
4. **DRIFT ANNOTATIONS:** any `path:line` staleness found in the sprint / task body (LESSON pattern from daybook).
5. **BLOCKERS:** tenant, upstream Commander, or design ambiguity — stop, do not guess.

---

## 8. Daybook alignment

- **Workers:** read Downloads `JOURNAL.md` / `LESSONS.md` silently; **no** edits unless task whitelists them.
- **Orchestrator (often human):** append one sprint block + rollup test count; run `sync_daybook.sh` after `JOURNAL`/`LESSONS` edits.
- **Distillation:** if sprint tail > ~2 screens, collapse older SDK sprints into one “burst” summary (per daybook skill).

---

## 9. Risk register (parallel-specific)

| Risk | Mitigation |
|------|------------|
| Duplicate work on same `$def` | R2a/R2b memos name **exact JSON pointers** they own. |
| Drift between memos and code | Integrator runs devil-check: “does board match `pytest` count?” |
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

## 11. Quick-launch checklist (integrator)

- [ ] Branch / merge train strategy chosen  
- [ ] Wave 1 workers launched (R1, R2a, R2b, R4 [+ R3])  
- [ ] Wave 2 triage complete; F* unlocked  
- [ ] Hot files assigned exclusively  
- [ ] Live tenant slot reserved for L1 only (one actor / tenant — human, CI, or granted agent)  
- [ ] Final integration: full pytest + ruff + mypy + (drift if touched)  
- [ ] `CHANGELOG.md` / `AGENTS.md` if user-visible CLI or support text changed  
- [ ] Daybook rollup line updated  

This plan is safe to attach to Codex / Cursor worker prompts as the **orchestration index**; slice-specific bodies stay in per-task prompts.

---

## 12. Large sprint mode (more scope, more orchestration)

**Yes — larger sprints work** if you treat them as a **program** (many small packages) rather than one big blob. What scales is **parallel readonly + serialized integration + explicit WIP limits**. What does *not* scale is “everyone edits `main` blind” or “many live tenants at once.”

### When to use large-sprint mode

- **Multi-track goals** in one calendar window (e.g. live-proof + P18 + two P11 slices + one report verb).
- **Enough integrator bandwidth** for triage: expect **~2×** the triage time of §3–§4 for each extra parallel *implementation* track, not for readonly memos.
- **SDK_DA still holds:** no widening “supported” without gates; large sprint = more **packages**, not looser proof.

### WIP limits (recommended defaults)

| Lane | Max parallel |
|------|----------------|
| Readonly memos (R\*) | **6** (cheap; conflict-free if outputs are external) |
| Foreground impl touching **different** path prefixes | **3** |
| Workers touching the **same** hot file (`main.py`, one `.schema.json`) | **1** |
| Open integration branches / merge trains | **2** (second only if first is green and idle) |
| Live lab sessions (**L1**) | **1** concurrent **actor / tenant** (human, CI, or granted agent — not “human only”) |

Exceed these only if you add a second **integration owner** who owns merge order.

### Program structure (add to small sprint)

1. **Program board** (one table): columns *Backlog → Memo done → Impl in flight → CI green → Merged*. Each row = one work package ID from §3 (or split F2 into F2a1, F2a2).
2. **Weekly (or mid-sprint) checkpoint**: collapse scope — what ships this train vs slips to next train; update JOURNAL “next queue” once.
3. **Trains**: e.g. **Train A** = schemas + tests only; **Train B** = CLI + report; **Train C** = `sync_upstream` + snapshots. Merge **A → B → C** order when B depends on A; A and C can be parallel **only if** C does not regenerate files A touches.

### Extra waves (typical 2-week shape)

| Day band | Focus |
|----------|--------|
| **D1** | Wave 0 + Wave 1 (all R\* in parallel) + start long-running R1 if heavy |
| **D2–D3** | Wave 2 triage; lock hot-file map; spawn F2a/F2b/F1 as unlocked |
| **D5** | Mid-sprint checkpoint; kill or defer lowest-priority row |
| **D8–D10** | L1 live window; F3 evidence; no new F\* starts unless train is green |
| **D12–D14** | Final integration train; distillation pass on JOURNAL if tail > 2 screens |

Adjust proportionally for 1-week vs 3-week; the **invariant** is **readonly burst first**, **impl second**, **live gate last**.

### Roles (lightweight — can all be one person)

| Role | Responsibility |
|------|----------------|
| **Integrator** | Merge train, hot-file exclusivity, final CI, SDK_DA wording (human or lead agent) |
| **Memo triage** | Resolve contradictions between R2a/R2b/R1; can be same as integrator |
| **Live runner** | L1: one lane per tenant — human **or** granted code (smoke / CI / agent); never parallel uncoordinated writers |

### Large-sprint success bar (stricter than §10)

Pick **four** of:

1. Two or more **F\*** packages merged with green full CI.
2. **R1** accepted and **F1** merged or honestly blocked with issue link.
3. **L1** executed **or** time-boxed deferral with exact next date in JOURNAL.
4. **Zero** undeclared hot-file merge conflicts (if any → LESSON entry).
5. Daybook rollup + board table match `pytest` count after merge.

### Failure mode to avoid

**“Orchestration theatre”** — many workers, no merge train, integrator drowning in partial diffs. Fix: **lower WIP**, freeze new F\* until current train merges, prefer another **readonly** wave instead.

---

## 13. Choosing sprint size (cheat sheet)

| Situation | Prefer |
|-----------|--------|
| Single slice, clear owner | Small sprint (§1–§11 only) |
| 2–3 disjoint path prefixes + memos ready | Medium = §11 + **half** of §12 (WIP table + one train) |
| Multi-track + calendar pressure | Large = full §12 + program board + mid-sprint checkpoint |

Larger sprints **increase orchestration overhead**; they do not replace proof, CI, or SDK_DA gates.

---

## 14. Planning a larger sprint **through** this document

Use this file as the **single procedure** (not a one-off essay). Order:

1. **Scope** — Write one sentence like §1 (sprint outcome). Pick size with §13.
2. **Board** — Copy rows from §3 (R\*, F\*) into JOURNAL / sheet / issue epic: each row = one assignable package with ID.
3. **Calendar** — Map wall time to §12 *Extra waves* (scale day bands to 1w / 2w / 3w).
4. **Wave 0** — §4 Wave 0: branch / merge train, post package table, pin CONVENTIONS + V2 Q1 in every worker prompt.
5. **Wave 1** — §4 Wave 1: launch all readonly packages in parallel; use preamble; **omit** “no keeper login” line only for tasks that explicitly grant live (§4 note).
6. **Wave 2** — §4 Wave 2: triage memos; assign §5 hot files; schedule **L1** actor (human, CI, or granted agent per top of doc).
7. **Wave 3** — §4 Wave 3 + §12 WIP limits: only as many F\* as caps allow; sequence `main.py` / single-schema conflicts.
8. **Live** — §4 Wave 4 + `docs/live-proof/README.md`: one tenant lane; sanitize before git.
9. **Merge** — §4 Wave 5 + §6 CI gates; integrator runs full pre-merge pass.
10. **Exit** — §12 large-sprint success bar (stricter) or §10 for smaller sprints.
11. **Close** — §11 checklist + §8 daybook (rollup line, `sync_daybook.sh` if you edit JOURNAL/LESSONS).

**Answer:** Yes — larger sprints are planned **by filling §3, then executing §4 with §12 limits, then closing with §10/§12 and §11.** No separate “big sprint” template is required beyond this path.
