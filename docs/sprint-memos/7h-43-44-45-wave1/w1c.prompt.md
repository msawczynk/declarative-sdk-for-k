# 7h-43 W1c — commander_cli cov: tests for lines 1234-3134

Worktree: `/Users/martin/Downloads/Cursor tests/worktrees/cursor-cov-cli-tests-C`, branch `cursor/cov-cli-tests-C`, base 8044bb8.

Goal: TESTS-ONLY for missing line ranges in **1234-3134** (long tail): `1234, 1238, 1291, 1525-1530, 1551, 1556, 1585, 1589, 1608-1611, 1615, 1646, 1655-1656, 1688, 1692, 1719-1720, 1730, 1737-1739, 1741-1742, 1752-1755, 1773, 1785, 1896, 1943-1944, 1986-1991, 2095-2096, 2139-2140, 2228-2229, 2274, 2299, 2306, 2357, 2370-2371, 2377, 2381-2382, 2386, 2390, 2393-2394, 2408, 2425-2427, 2449-2450, 2458, 2560, 2575, 2657, 2742, 2790, 2803, 2811-2815, 2835, 2847, 2881, 2917, 2939-2940, 2966, 2982, 2990-2993, 3018, 3075, 3077, 3081, 3131-3132, 3134`.

# Required reading
- `keeper_sdk/providers/commander_cli.py` lines 1200-end (full read; this is sharing methods + late helpers).
- `tests/test_commander_cli_sharing.py` (V7b's stubbed sharing tests — many of YOUR target lines may already be near these).
- `tests/test_commander_cli.py`.

# Hard requirements
1. NEW file `tests/test_commander_cli_cov_c.py`. ~25-45 cases (long tail, many small ranges).
2. Each missing line cited in test docstring.
3. NO prod code edits. NO modifications to V7b's `test_commander_cli_sharing.py`.
4. The sharing methods (lines ~2000-2400) likely overlap with V7b's coverage; focus on missing branches V7b skipped (error paths, ValueError on contradictory inputs, etc.).
5. `_run_cmd` monkeypatch + canned JSON; raise paths.

# Workflow
1. Read source + V7b's existing sharing tests.
2. For each missing-line cluster, design test case.
3. Iterate; ruff; mypy.
4. `python3 -m pytest --cov=keeper_sdk.providers.commander_cli --cov-report=term-missing -q tests/test_commander_cli*.py` — confirm your cluster covered.
5. Full suite: target +25-45 tests.
6. `git add -A && git commit -m "test(commander_cli): cov 1234-3134 long-tail slice (7h-43 W1c)"`.
7. `git push -u origin cursor/cov-cli-tests-C`.
8. Output `DONE: cursor/cov-cli-tests-C <sha>` or `FAIL: <one-line>`.

# Constraints
- No prod edits.
- Disjoint from W1a (100-620) and W1b (776-1163).
- Combined target across A+B+C: lift commander_cli.py cov from 81% to ≥90%.
