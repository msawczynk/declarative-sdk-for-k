# 7h-45 V8c — vaultSharingLifecycle offline tests

Worktree: `/Users/martin/Downloads/Cursor tests/worktrees/cursor-sharing-tests`, branch `cursor/sharing-tests`, base 8044bb8.

Goal: NEW test file `tests/test_smoke_sharing_lifecycle.py`. Pin scenario shape + smoke runner contract for `vaultSharingLifecycle`. Offline only (mock provider). NO scenarios.py edit, NO smoke.py edit.

# Required reading
- `scripts/smoke/scenarios.py` (read; V8a is appending VAULT_SHARING_LIFECYCLE constant).
- `scripts/smoke/smoke.py` (read; V8b is adding dispatch).
- Existing test pattern: `tests/test_smoke_*.py` if any, else `tests/test_sharing_mock_provider*.py` for offline round-trip patterns.
- LESSON `[orchestration][parallel-write-3way-conflict-pattern]`.

# Hard requirements
1. NEW `tests/test_smoke_sharing_lifecycle.py`. ~10-15 cases:
   - `import scripts.smoke.scenarios as scenarios` + assert `VAULT_SHARING_LIFECYCLE` exists with name="vaultSharingLifecycle", family="keeper-vault-sharing.v1".
   - Resource factory builds the expected payload shape.
   - Verifier accepts a happy-path record list.
   - Verifier raises on missing folder marker.
   - Verifier raises on missing shared_folder.
   - Verifier raises on missing record_share grantee.
   - Verifier raises on missing share_folder.
   - End-to-end mock-provider round-trip: build manifest from resources, plan, apply, discover, re-diff = 0 changes.
   - Round-trip with allow_delete=True from clean state = 0 changes.
   - Edge case: 2 record_shares same record different grantees.

2. The tests can fail-import gracefully if V8a hasn't merged yet — use `pytest.importorskip` or guard with `pytest.mark.skipif(not hasattr(scenarios, 'VAULT_SHARING_LIFECYCLE'), reason='V8a not landed')`. Once V8a merges, the skip clears.

# Workflow
1. Read sources.
2. Write tests.
3. `python3 -m pytest -q --no-cov tests/test_smoke_sharing_lifecycle.py` — initially may skip (if V8a not landed locally yet); once V8a/V8b on `main`, must pass.
4. ruff format + check.
5. mypy.
6. Full suite green; cov stays ≥85%.
7. `git add -A && git commit -m "test(smoke): vaultSharingLifecycle offline tests (7h-45 V8c)"`.
8. `git push -u origin cursor/sharing-tests`.
9. Output `DONE: cursor/sharing-tests <sha>` or `FAIL: <one-line>`.

# Constraints
- ONLY new file `tests/test_smoke_sharing_lifecycle.py`.
- NO modifications to scripts/smoke/scenarios.py (V8a) or smoke.py (V8b) or any other file.
- Disjoint from V8a + V8b + W1a/b/c + W3 + W4.
