# 7h-43 W1a — commander_cli cov: tests for lines 100-620

Worktree: `/Users/martin/Downloads/Cursor tests/worktrees/cursor-cov-cli-tests-A`, branch `cursor/cov-cli-tests-A`, base 8044bb8.

Goal: TESTS-ONLY for `keeper_sdk/providers/commander_cli.py` missing line ranges in **100-620**: `100, 111-112, 120, 122, 133, 140, 163, 165, 169, 205, 214, 238, 246, 256, 274, 281-303, 318-355, 402, 405-407, 416-418, 425-426, 429-430, 474, 563, 619-620`. NO prod code edits.

# Required reading
- `keeper_sdk/providers/commander_cli.py` lines 1-650 (full read).
- `tests/test_commander_cli.py` (existing patterns: `_run_cmd` monkeypatch, `CommanderCliProvider` fixture).
- `tests/test_commander_cli_helpers.py` (helper-module pattern).
- LESSON `[orchestration][parallel-write-3way-conflict-pattern]` 7h-39 — strict file boundary.

# Hard requirements
1. NEW file `tests/test_commander_cli_cov_a.py`. ~25-40 cases.
2. Each missing line cited in test docstring (e.g. `# covers L205 (early-return path on empty payload)`).
3. Use `monkeypatch.setattr(provider, "_run_cmd", ...)` or `pytest.raises(...)` to drive missing branches.
4. NO production-code edits. NO modifications to existing test files.
5. NO new test fixtures touching live tenant.

# Workflow
1. Read source + existing tests.
2. For each missing-line cluster, design ONE test case that drives the branch.
3. Iterate `python3 -m pytest -q --no-cov tests/test_commander_cli_cov_a.py` until green.
4. `python3 -m pytest --cov=keeper_sdk.providers.commander_cli --cov-report=term-missing -q tests/test_commander_cli*.py` — confirm your cluster of lines now covered.
5. `python3 -m ruff format tests/test_commander_cli_cov_a.py && python3 -m ruff check keeper_sdk tests`.
6. `python3 -m mypy tests/test_commander_cli_cov_a.py`.
7. Full suite: `python3 -m pytest -q --no-cov`. Baseline 717+1; target +25-40.
8. `git add -A && git commit -m "test(commander_cli): cov 100-620 range slice (7h-43 W1a)"`.
9. `git push -u origin cursor/cov-cli-tests-A`.
10. Output `DONE: cursor/cov-cli-tests-A <sha>` or `FAIL: <one-line>`.

# Constraints
- Caveman commit body.
- No prod edits.
- Disjoint from W1b (lines 776-1163) and W1c (lines 1234+).
