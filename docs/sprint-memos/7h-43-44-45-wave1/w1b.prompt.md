# 7h-43 W1b — commander_cli cov: tests for lines 776-1163

Worktree: `/Users/martin/Downloads/Cursor tests/worktrees/cursor-cov-cli-tests-B`, branch `cursor/cov-cli-tests-B`, base 8044bb8.

Goal: TESTS-ONLY for missing line ranges in **776-1163**: `776-777, 781, 790, 806, 816, 826-834, 854-862, 864-872, 893-936, 939, 948, 982, 985-986, 994-1003, 1017-1019, 1029-1103, 1110-1163`. Largest cluster — biggest cov ROI.

# Required reading
- `keeper_sdk/providers/commander_cli.py` lines 700-1200 (full read).
- `tests/test_commander_cli.py` patterns.

# Hard requirements
1. NEW file `tests/test_commander_cli_cov_b.py`. ~30-50 cases (biggest of A/B/C).
2. Each missing line cited in test docstring.
3. NO prod code edits.
4. Heavy `_run_cmd` monkeypatch use; canned JSON returns; `pytest.raises(CapabilityError|ValueError|RuntimeError|...)` on error branches.
5. Lines 893-936, 1029-1103, 1110-1163 are the three big clusters — likely full-method-body coverage of one method each. Read 880-940, 1020-1110, 1100-1170 carefully to identify which method each cluster covers.

# Workflow
1. Read source + existing tests.
2. Design test cases per cluster.
3. Iterate `python3 -m pytest -q --no-cov tests/test_commander_cli_cov_b.py`.
4. `python3 -m pytest --cov=keeper_sdk.providers.commander_cli --cov-report=term-missing -q tests/test_commander_cli*.py`.
5. ruff format + check; mypy clean.
6. Full suite: target +30-50 tests.
7. `git add -A && git commit -m "test(commander_cli): cov 776-1163 range slice (7h-43 W1b)"`.
8. `git push -u origin cursor/cov-cli-tests-B`.
9. Output `DONE: cursor/cov-cli-tests-B <sha>` or `FAIL: <one-line>`.

# Constraints
- No prod edits.
- Disjoint from W1a (lines 100-620) and W1c (lines 1234+).
