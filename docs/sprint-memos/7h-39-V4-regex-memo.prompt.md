## Sprint 7h-39 V4 — agent_review_loop.py regex tightening memo (codex readonly)

You are a codex CLI **readonly** worker. Pending item from Sprint 7h-35 LESSON `[daybook][regex-by-reference-inflation]`. Produce a concrete patch + test plan for tightening the `pending_journal_items` regex so it stops matching historical references and self-referential explanatory text.

# Required reading

1. `/Users/martin/.cursor-daybook-sync/scripts/agent_review_loop.py` — full read; locate `pending_journal_items` calculation (currently a 1-line list-comprehension regex).
2. `/Users/martin/Downloads/JOURNAL.md` — line ranges where `Pending decisions` appears today (post-Sprint 7h-37 cleanup); count current matches.
3. `/Users/martin/Downloads/LESSONS.md` — entry `[daybook][regex-by-reference-inflation]` (Sprint 7h-35).
4. `/Users/martin/Downloads/Cursor tests/WORKTREES.md` — the canonical "Pending decisions" section that the regex SHOULD match.

# Deliverable

Produce a single memo (~80 lines) with:

## Section 1: Current regex audit

Cite the regex line in `agent_review_loop.py`. Show what it matches today by running it (mentally; no shell exec needed since you're readonly) against:
- `JOURNAL.md` — should match 0 (post-cleanup).
- `WORKTREES.md` — should match 1 section header + N items underneath.
- `LESSONS.md` — should match 0.

If you find drift (e.g., post-7h-38 journal entry uses "Pending decisions" again), cite line numbers.

## Section 2: Proposed regex

Replace with a 2-condition match:
- Match line if `re.match(r"^[-*]\s*\[\s\]", line)` (unchecked checkbox) AND the line is within a `## Pending decisions` section (track section state across lines).
- OR match line if `re.match(r"^\s*\d+\.\s+", line)` AND within a `## Pending decisions` section header in `WORKTREES.md`.

Or simpler alternative: extract the count from a single canonical source (`WORKTREES.md` § "Pending decisions" enumeration) instead of regex-scanning JOURNAL.

Recommend the simpler one if WORKTREES.md is authoritative.

## Section 3: Patch (unified diff)

Provide a unified diff for `agent_review_loop.py` showing the exact change. Cite the current line numbers.

## Section 4: Test plan

Three test cases (offline, no daybook write):
1. JOURNAL.md historical reference → not counted.
2. Self-referential explanatory text in a sprint summary mentioning "Pending decisions" → not counted.
3. WORKTREES.md `## Pending decisions` section with 3 unchecked items → count = 3.

Specify a small standalone test script `~/.cursor-daybook-sync/scripts/test_pending_count.py` that imports the function and asserts.

## Section 5: Migration risk

What breaks if the regex changes? Search for callers of `pending_journal_items` in the daybook scripts (you can use Grep tool). Any session-boot hook that reads it? Any consumer formatting that depends on its current behavior?

## Section 6: CANDIDATE LESSON

Format: `2026-04-27 [daybook][regex-tightening] <one line>`.

# Constraints

- Read-only.
- Cite file:line for every claim.
- Output the full memo as your final response.
- Do not modify any files.
