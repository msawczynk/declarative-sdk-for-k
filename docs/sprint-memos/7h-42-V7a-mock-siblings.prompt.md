<!-- Generated from templates/SPRINT_offline-write-feature.md, version 2026-04-27 -->

## Sprint 7h-42 V7a — sharing.v1 mock provider sibling-block apply (codex offline write)

Worktree: `/Users/martin/Downloads/Cursor tests/worktrees/cursor-sharing-mock-siblings`, branch `cursor/sharing-mock-siblings`, base `674f2b3`.

# Goal

Extend `MockProvider` so the 3 sharing.v1 sibling blocks (`shared_folders`, `share_records`, `share_folders`) round-trip through apply/discover. V6a proved generic dispatch suffices for folders. Sibling rows are different — `record_shares` and `share_folders` are RELATIONAL (no record body to mark, marker lives on parent shared_folder per V6d memo §5). Either:

- **Path A (preferred per V6d memo)**: store sibling state directly on the parent shared_folder LiveRecord's payload (e.g. `payload["record_shares"]: [...]` / `payload["share_folder_grants"]: [...]`). Diff helpers already match by `(record_uid_ref, grantee)` / `(shared_folder_uid_ref, kind, ...)` — apply mutates parent's payload list.
- **Path B (fallback)**: separate stores `_share_records: list[dict]` / `_share_folder_grants: list[dict]` on `MockProvider`. Diff and discover thread them as keyword args.

Pick one based on what minimizes V7c CLI dispatch complexity. Document the choice in commit body.

# Required reading

1. `keeper_sdk/providers/mock.py` (207 LOC) — full read; V6a left it unchanged. Note `apply_plan()` dispatches by ChangeKind only.
2. `keeper_sdk/core/sharing_diff.py` (~1300 LOC post-V6b) — full read of the 3 new helpers `_compute_shared_folders_changes`, `_compute_record_shares_changes`, `_compute_share_folders_changes`. Note resource_type strings: `"sharing_shared_folder"`, `"sharing_record_share"`, `"sharing_share_folder"`.
3. `keeper_sdk/core/sharing_models.py` — full read.
4. `tests/test_sharing_mock_provider.py` (V6a, 10 cases) — pattern for round-trip tests.
5. `tests/test_sharing_diff_shared_folders.py`, `tests/test_sharing_diff_record_shares.py`, `tests/test_sharing_diff_share_folders.py` (V6b, 12 each) — fixtures to reuse.
6. `keeper_sdk/core/interfaces.py` — `LiveRecord`, `ApplyOutcome`, `Provider` protocol. If you add a `discover_*` method for siblings, decide whether to extend `Provider`.
7. LESSON `[orchestration][generic-mock-suffices]` 7h-41 — start with TESTS-only; only modify mock.py if tests fail.
8. V6d memo (`docs/sprint-memos/7h-41-V6d-roadmap.codex.log` lines covering §1 + §5) — sibling marker storage policy.

# Hard requirements

## Strategy decision (write to commit body)

1. Read sources above. Pick Path A or Path B with a 2-3 sentence justification.
2. If Path A, find the existing CREATE handler in `mock.py:60-87`; sibling Change rows from V6b will arrive with `resource_type ∈ {sharing_shared_folder, sharing_record_share, sharing_share_folder}`. Either treat each as its own LiveRecord (unified) OR mutate parent. Document the choice.

## Tests — `tests/test_sharing_mock_provider_siblings.py` (NEW; ~18 cases)

3. **shared_folder CREATE → discover → re-diff clean**: 1 manifest shared_folder, empty mock → 1 ADD apply, post-apply discover returns marker-bearing payload, re-diff via `compute_sharing_diff(manifest, live_shared_folders=...)` returns 0 actionable changes.
4. **shared_folder UPDATE**: drift on `name` / `default_can_edit` → UPDATE applies → discover reflects new value.
5. **shared_folder DELETE allow_delete=True**: marker-ours, manifest empty → DELETE → discover empty.
6. **shared_folder SKIP unmanaged**: marker `manager != MANAGER_NAME` → SKIP, no apply outcome that mutates state.
7. **record_share CREATE → discover → re-diff clean**: 1 manifest record_share, empty mock → 1 ADD apply.
8. **record_share UPDATE**: permissions drift (`can_edit` flip) → UPDATE → discover reflects.
9. **record_share DELETE allow_delete=True**: → DELETE → discover empty for that key.
10. **record_share grantee key disambiguation**: 2 manifest record_shares for same record, different grantees (user A vs user B) → 2 ADDs, both succeed, discover returns both.
11. **share_folder grantee_share CREATE/UPDATE/DELETE**: 3 cases.
12. **share_folder record_share CREATE/UPDATE/DELETE**: 3 cases.
13. **share_folder default_share CREATE/UPDATE**: 2 cases.
14. **share_folder default_share collision**: 2 manifest default_shares for same shared_folder → ValueError on diff (matches V6b's per-block ValueError pattern).
15. **mixed manifest round-trip**: manifest with 2 folders + 1 shared_folder + 1 record_share + 2 share_folders (one grantee + one default) → all CREATE → re-diff via combined `compute_sharing_diff(manifest, live_folders=..., live_shared_folders=..., live_share_records=..., live_share_folders=...)` returns 0 actionable.
16. **dry_run** for each block → outcome generated, no state mutation.

## If `mock.py` modification required

17. Minimal extension only. Document in commit body. Add a regression test FIRST. Do NOT refactor existing folder/PAM/vault apply logic.

## Workflow

1. Read all listed files end-to-end.
2. Write tests; iterate `python3 -m pytest -q --no-cov tests/test_sharing_mock_provider_siblings.py` until green.
3. `python3 -m ruff format <touched files> && python3 -m ruff check keeper_sdk tests`. Fix.
4. Full suite: `python3 -m pytest -q --no-cov`. Baseline 663+1; target +18 → 681+1.
5. `python3 -m pytest -q --cov=keeper_sdk --cov-fail-under=85`. Must stay above 85.
6. `python3 -m mypy <touched files>`. Clean.
7. `git add -A && git commit -m "feat(sharing-v1): mock provider sibling-block apply (shared_folders + record_shares + share_folders)"`.
8. `git push -u origin cursor/sharing-mock-siblings`.
9. Output `DONE: cursor/sharing-mock-siblings <sha>` or `FAIL: <one-line>`.

## Constraints

- Caveman-ultra commit body, MUST document Path A vs B choice.
- No live tenant.
- Marker manager UNTOUCHED.
- Do not re-add `ChangeKind.ADD`/`SKIP`.
- Do not modify `keeper_sdk/core/sharing_diff.py` (V7b is editing nothing here, but V6b's invariants must hold).
- Do not modify `keeper_sdk/providers/commander_cli.py` (V7b territory).
- Do not modify `keeper_sdk/core/manifest.py` or `keeper_sdk/cli/main.py` (V7c territory).

# Anti-patterns to avoid (LESSONS-derived)

- LESSON `[orchestration][parallel-write-3way-conflict-pattern]` 7h-39 — strict file boundary; if tempted to edit beyond mock.py + new test file, STOP and re-read this prompt.
- LESSON `[orchestration][generic-mock-suffices]` 7h-41 — try tests-first; only patch mock.py if tests force it.
- LESSON `[smoke][marker-manager-is-core-contract]` — every CREATE must round-trip with `MANAGER_NAME` intact.
- LESSON `[capability-census][three-gates]` — when V7a closes, sharing.v1 mock provider gate is met for all 4 blocks (folder + 3 siblings).
