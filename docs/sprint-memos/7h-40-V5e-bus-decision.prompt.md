## Sprint 7h-40 V5e — bus.py decision finalisation (codex readonly memo)

You are a codex CLI **readonly** worker. WORKTREES.md §7 has been pending since Sprint 7h-9/7h-10; Sprint 7h-35 worker memo (`71504ca0`) recommended Option A/B/C with conditions. The orchestrator now wants a **decision-finalisation memo** that:

1. Re-confirms the 7h-35 worker's three-option analysis is still valid against the current `main` (commit `306cb26`).
2. Resolves the two PARENT-DECIDE items WORKTREES §7 lists.
3. Produces a concrete patch (or pragma block) for the chosen option that the orchestrator can apply directly.

# Required reading

1. `keeper_sdk/secrets/bus.py` — full read (currently 225 LOC; check actual line count). Confirm: `BusClient` + `BusMessage` dataclass, 5 public methods raising `CapabilityError`, Phase B checklist in module docstring at lines 97:117.
2. `keeper_sdk/exceptions.py` (or wherever `CapabilityError` lives) — confirm raise sites point at the right exception class.
3. `pyproject.toml` — find `[tool.coverage.*]` (likely absent), `[tool.pytest.ini_options]`, and the CI floor `--cov-fail-under=84`.
4. `.coveragerc` — likely absent.
5. `.github/workflows/ci.yml` — `--cov-fail-under` flag at ~ line 64.
6. WORKTREES.md §7 — full read.
7. `/Users/martin/Downloads/JOURNAL.md` Sprint 7h-9 + 7h-10 entries — find the cov-bus-skeleton history; specifically the 7h-10 F4 LESSON re: metric-gaming.
8. `/Users/martin/Downloads/LESSONS.md` `[coverage][sealed-skeleton]` entry — the worker recommendation Sprint 7h-35 captured.
9. `git log --all --oneline | grep -i bus` — find PR #24 / `cursor/cov-bus-skeleton` SHAs to verify subsumed-or-not.

# Deliverable: ~120-line decision memo + patch

## Section 1: Current state audit

Cite each:
- `bus.py` LOC, public method count, exception type. Confirm matches 7h-35 memo.
- Phase B checklist items (6 per 7h-35 memo). Cite line range.
- Caller search: `grep -rn "from keeper_sdk.secrets.bus import\|keeper_sdk.secrets.bus" keeper_sdk tests scripts docs` — confirm zero internal callers. (Use the Grep tool.)
- `pyproject.toml`/`.coveragerc` state for omit/exclude lists.

## Section 2: Resolve PARENT-DECIDE (i) — 7h-9/10 PR #24 reconciliation

Use `git log` + `git show` to determine:
- Is `cursor/cov-bus-skeleton` still on origin? (`git ls-remote origin cursor/cov-bus-skeleton`.)
- Was it merged? Check `git log --all --grep="cov-bus" --oneline`.
- Does `tests/test_bus.py` exist on current `main`? If yes, what's its content (cite line count).
- Verdict: **SUBSUMED**, **STILL OPEN**, or **ABANDONED**.

## Section 3: Resolve PARENT-DECIDE (ii) — exception-type text fix

WORKTREES §7 was textually corrected in Sprint 7h-35 (`NotImplementedError` → `CapabilityError`). Confirm the current text is correct by reading WORKTREES.md §7 directly. If still wrong, propose the exact diff.

## Section 4: Recommend A vs B vs C

Pick ONE based on the audit:

- **A** = implement Phase B (full feature). Cost: 6-step checklist, ~400 LOC + tests + docs + CLI. Justify only if KSM bus is on the near-term roadmap.
- **B** = `CapabilityError` stub coverage. Cost: ~20 LOC test file. Already explored 7h-9/10; flagged as metric-gaming. Justify only if cov number absolutely must include this module.
- **C** = exclude from coverage via `# pragma: no cover` per-method OR `[tool.coverage.run] omit = ["keeper_sdk/secrets/bus.py"]`. Cost: 1 line config OR ~6 pragma comments. Justify if Phase B is parked indefinitely.

State your recommendation explicitly: `RECOMMEND: <A|B|C>`.

## Section 5: Patch for chosen option

Provide a unified diff:

- For C-omit: `pyproject.toml` adds `[tool.coverage.run] omit = ["keeper_sdk/secrets/bus.py"]`.
- For C-pragma: `bus.py` adds `# pragma: no cover` to each `raise CapabilityError(...)` line.
- For B: `tests/test_bus_capability_error.py` NEW — 5 tests asserting each method raises `CapabilityError`.
- For A: out of scope for this memo — produce a phase-B implementation plan instead, NOT the implementation itself.

Provide the patch in unified diff format that orchestrator can `git apply`.

## Section 6: Coverage impact prediction

If C-omit:
- `bus.py` 0% → excluded entirely; total cov number rises by `(225 / total_LOC_under_cov) * (current_uncovered_pct) = ?%`. Cite total LOC under cov.
- This unlocks Pending §8 (cov ratchet 84 → 85)? State exact prediction.

If C-pragma:
- Each pragma line excluded from cov. ~5 lines excluded. Smaller bump.

If B:
- 5 new test cases each cover 1 raise line. Maybe 10 LOC of bus.py becomes covered. Tiny effect on total.

## Section 7: CANDIDATE LESSON

`2026-04-27 [coverage][bus-decision-finalised] <one-line>`.

# Constraints

- Read-only.
- Cite file:line for every non-trivial claim.
- Output the full memo as your final response.
- Do not modify any files.
- If you discover that the audit reveals state different from what 7h-35 memo claimed, FLAG it explicitly and re-baseline.
