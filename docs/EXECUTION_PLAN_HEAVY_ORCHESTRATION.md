# Execution plan — heavily orchestrate & continue

**Intent:** Time-ordered **checklist** to continue the PAM parity program without
scope creep. **Flight deck + PR train:** [`ORCHESTRATION_PAM_PARITY.md`](./ORCHESTRATION_PAM_PARITY.md).
**Wave mechanics + R/F IDs:** [`NEXT_SPRINT_PARALLEL_ORCHESTRATION.md`](./NEXT_SPRINT_PARALLEL_ORCHESTRATION.md).
**Run until program exit (tiers, ledger, waves):**
[`ORCHESTRATION_UNTIL_COMPLETE.md`](./ORCHESTRATION_UNTIL_COMPLETE.md).

**Daybook:** After Phase 0 below, append a short status block to
`~/Downloads/JOURNAL.md` under `declarative-sdk-for-k` (test count, active branch,
link to this file). Do **not** paste daybook bodies into the SDK repo.

---

## Phase 0 — Integrator cold start (≤ 60 min, blocking)

Do these **before** dispatching workers.

| # | Action | Done |
|---|--------|:----:|
| 0.1 | Read [`ORCHESTRATION_PAM_PARITY.md`](./ORCHESTRATION_PAM_PARITY.md) §1–§3 + [`PAM_PARITY_PROGRAM.md`](./PAM_PARITY_PROGRAM.md) gates | ☐ |
| 0.2 | Read [`NEXT_SPRINT_PARALLEL_ORCHESTRATION.md`](./NEXT_SPRINT_PARALLEL_ORCHESTRATION.md) §0–§3 (preambles, serialization rules) | ☐ |
| 0.3 | `git fetch && git status` on integration branch; confirm **one** live-tenant owner for upcoming L1 | ☐ |
| 0.4 | Update **Downloads** `JOURNAL.md`: SDK snapshot (pytest count, Phase 0/1a shipped, link **this** file + orchestration hub); reconcile stale V1 “examples missing” line if still present | ☐ |
| 0.5 | Post **WORK PACKAGE TABLE** (Phase A) to your orchestration channel with worker IDs | ☐ |

---

## Phase A — Parallel burst (calendar days 1–3, mostly readonly)

**Goal:** Land **PR-V0** (`docs/VAULT_L1_DESIGN.md` completed + reviewed) **or**
document a blocker using [`ORCHESTRATION_PAM_PARITY.md`](./ORCHESTRATION_PAM_PARITY.md) §8 template.

| Package | Owner | Deliverable | Merge? |
|---------|-------|-------------|--------|
| **V0** | Integrator + 1 reviewer | Fill [`VAULT_L1_DESIGN.md`](./VAULT_L1_DESIGN.md): scope, folder UID, markers, discover→`LiveRecord`, plan semantics, out-of-scope | PR to `main` |
| **R1** | Worker | P18 extractor / allowlist memo per [`P18_SYNC_UPSTREAM_EXTRACTOR_DECISION.md`](./P18_SYNC_UPSTREAM_EXTRACTOR_DECISION.md) | Memo / doc PR |
| **R2a** | Worker | P11 slice memo (e.g. enforcements) — disjoint file areas | Memo |
| **R2b** | Worker | P11 slice memo (e.g. aliases) — **must not** overlap R2a | Memo |
| **R4** | Worker | Live-proof checklist delta in `docs/live-proof/` **only if** maintainer allows doc edit | Memo or small PR |

**Dispatch:** Use preambles in [`ORCHESTRATION_PAM_PARITY.md`](./ORCHESTRATION_PAM_PARITY.md) §5.

**Exit criteria:** V0 merged **or** JOURNAL blocker with owner + next date.

**Forbidden in Phase A:** edits to `commander_cli.py`, new `dsk report` verbs, new
top-level orchestration **scripts** inside this repo (scope-fence per daybook).

---

## Phase B — Vault offline vertical (days 3–12, serial merge train)

**Precondition:** V0 merged.

| PR | Focus | CI gate |
|----|--------|---------|
| **V1** | Typed vault models + unit tests only | `pytest` + `ruff` + `mypy` |
| **V2** | Vault graph / `uid_ref` rules | same |
| **V3** | `MockProvider` discover + diff + plan for **one** minimal vault fixture | same + **no** change to examples plan job yet |

**Integrator after each merge:** full `python3 -m pytest -q`, `ruff check .`,
`ruff format --check .`, `mypy keeper_sdk`.

**Exit criteria:** V3 green; mock plan path demonstrable in tests (fixture-driven).

---

## Phase C — CLI dispatch (days 10–14, one design-locked PR)

**Precondition:** V3 merged; V0 answers **how** `plan`/`load_manifest` sees vault
(one chosen approach — do not dual-path).

| PR | Focus | CI gate |
|----|--------|---------|
| **V4** | Single entry strategy (`load_manifest` dispatch **or** explicit sub-flag) + `AGENTS.md` one paragraph | full suite + update [`VALIDATION_STAGES.md`](./VALIDATION_STAGES.md) if behaviour changes |

**Exit criteria:** `dsk plan` (or documented equivalent) runs for vault fixture
**offline**; **then** extend CI per orchestration hub **§7** (mock plan for one
scaffold vault file **only** when safe).

---

## Phase D — Commander + tenant (days 14–25, strictly serialized)

**Precondition:** V4 merged; lab tenant slot booked.

| PR | Focus | Notes |
|----|--------|------|
| **V5** | Commander **discover** for vault slice | Mocked tests + minimal live smoke optional |
| **V6** | Commander **apply** + delete policy | Contract tests; live proof rehearsal |
| **L1** | Sanitized transcript + evidence file | **One** actor on tenant; follow `docs/live-proof/README.md` |

**Exit criteria:** V6 green offline; L1 artifact exists and is linked from schema
draft (prep for V8).

---

## Phase E — Sharing + proof closure (days 20–35)

| PR | Focus |
|----|--------|
| **V7** | `keeper-vault-sharing` models / graph / mock / Commander — reuse vault patterns |
| **V8** | `x-keeper-live-proof`, matrix row, README readiness row **only** when PAM bar satisfied |

**Exit criteria:** README “Readiness” rows flip **or** explicit deferral with
un-drop triggers logged in JOURNAL.

---

## Parallel lanes (non-blocking the critical path)

Run anytime **after Phase 0**, respecting [`NEXT_SPRINT`](./NEXT_SPRINT_PARALLEL_ORCHESTRATION.md) §2 serialization.

| Lane | When | Owner |
|------|------|-------|
| **F1 / P18c** | After R1 accepted | Worker + integrator merge |
| **F2a / F2b** | After R2a/R2b | Two workers, disjoint paths |
| **F4 report** | After R3 memo only | Single worker (touch `cli/_report/`, `main.py`) |

Do **not** let F\* work **block** V1–V3; if conflicts arise, **vault train wins**
until V3 is merged.

---

## Metrics (cheap health checks)

| Metric | Target |
|--------|--------|
| Open PRs touching `commander_cli.py` | ≤ **1** at a time during Phase D |
| New top-level `docs/*.md` per week | ≤ **2** unless integrator approves (avoid doc sprawl) |
| `main` green | **100%** between merges |
| JOURNAL SDK snapshot age | ≤ **7 days** during active sprint |

---

## Sprint close (mandatory)

| # | Action |
|---|--------|
| S.1 | Run [`NEXT_SPRINT_PARALLEL_ORCHESTRATION.md`](./NEXT_SPRINT_PARALLEL_ORCHESTRATION.md) **§16** review |
| S.2 | Update [`PAM_PARITY_PROGRAM.md`](./PAM_PARITY_PROGRAM.md) inventory table for any family that moved |
| S.3 | LESSON / JOURNAL entry: what to **stop** doing next sprint (scope, merge, or delegation) |

---

## One-line “continue” prompt for agents

```text
Execute docs/EXECUTION_PLAN_HEAVY_ORCHESTRATION.md: complete Phase 0 checkboxes,
then the next open Phase (A→E); cite ORCHESTRATION_PAM_PARITY §3 PR id in commits;
do not expand scope beyond VAULT_L1_DESIGN.md slice-1.
```
