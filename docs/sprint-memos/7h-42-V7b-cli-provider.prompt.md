<!-- Generated from templates/SPRINT_offline-write-feature.md, version 2026-04-27 -->

## Sprint 7h-42 V7b — `CommanderCliProvider` sharing methods (codex offline write)

Worktree: `/Users/martin/Downloads/Cursor tests/worktrees/cursor-sharing-cli-provider`, branch `cursor/sharing-cli-provider`, base `674f2b3`.

# Goal

Add explicit Commander CLI methods for sharing.v1 to `CommanderCliProvider`, stubbed against `_run_cmd` argv assertions (offline). Concrete Commander upstream commands cited in V6d memo (`docs/sprint-memos/7h-41-V6d-roadmap.codex.log`). Out of scope: live tenant; CLI plan/apply dispatch wiring (V7c); mock provider extension (V7a).

# Required reading

1. `keeper_sdk/providers/commander_cli.py` (1700+ LOC) — read at minimum:
   - lines 1-100 (module docstring, command list)
   - lines 1290-1330 (existing `_ensure_folder_exists`, `_ensure_shared_folder_exists`, `_share_folder_to_ksm_app`)
   - lines 1602-end (`_run_cmd` definition + helpers)
   - lines 200-260 (existing `discover` / `ls --format json` patterns)
2. `.venv/lib/python3.14/site-packages/keepercommander/commands/folder.py` — find `mkdir`, `mv`, `rmdir` parsers. Cite line numbers for the flag definitions you'll use.
3. `.venv/lib/python3.14/site-packages/keepercommander/commands/register.py` — find `share-record`, `share-folder` parsers. Cite flag definitions.
4. V6d memo: `docs/sprint-memos/7h-41-V6d-roadmap.codex.log` Section 2 — definitive command-list and Commander source-of-truth lines.
5. `keeper_sdk/core/sharing_diff.py` (post-V6b) — Change rows your methods will eventually consume. Resource type strings: `sharing_folder`, `sharing_shared_folder`, `sharing_record_share`, `sharing_share_folder`.
6. Existing test pattern: `tests/test_commander_cli.py` for `_run_cmd` argv assertion style.
7. LESSON `[orchestration][generic-mock-suffices]` 7h-41 — V7b is the Commander analog: stubbed argv assertions BEFORE wiring into `apply_plan`.

# Hard requirements

## Methods — `keeper_sdk/providers/commander_cli.py` (EDIT)

Add these methods on `CommanderCliProvider` (place them adjacent to `_ensure_folder_exists` for cohesion):

1. **`_create_user_folder(self, *, path: str, parent_uid: str | None = None, color: str | None = None) -> None`**
   - argv: `["mkdir", "-uf", "<path>"]` plus `["--color", color]` if non-None. Parent placement is implicit via path prefix.
2. **`_create_shared_folder(self, *, path: str, manage_records: bool = True, manage_users: bool = True, can_edit: bool = True, can_share: bool = True) -> None`**
   - argv: `["mkdir", "-sf"]` plus `["--manage-records"]` / `["--manage-users"]` / `["--can-edit"]` / `["--can-share"]` flags conditionally, then `[path]`.
3. **`_move_folder(self, *, source: str, destination: str, is_shared: bool = False) -> None`**
   - argv: `["mv", "--shared-folder" if is_shared else "--user-folder", source, destination]`.
4. **`_delete_folder(self, *, path_or_uid: str) -> None`**
   - argv: `["rmdir", "-f", path_or_uid]`.
5. **`_share_record_to_user(self, *, record_uid: str, user_email: str, can_edit: bool, can_share: bool, expiration_iso: str | None = None) -> None`**
   - argv: `["share-record", "-a", "grant", "-e", user_email]` plus `["-p" if can_edit else "..."]` etc per Commander parser. CITE the parser line in commit body.
6. **`_revoke_record_share_from_user(self, *, record_uid: str, user_email: str) -> None`**
   - argv: `["share-record", "-a", "revoke", "-e", user_email, record_uid]`.
7. **`_share_folder_to_grantee(self, *, shared_folder_uid: str, grantee_kind: Literal["user","team","default"], identifier: str | None = None, manage_records: bool, manage_users: bool) -> None`**
   - argv: `["share-folder", "<shared_folder_uid>", "-a", "grant", "-e" or "-t" or "--default-account", identifier_or_none, ...]`.
8. **`_revoke_folder_grantee(self, *, shared_folder_uid: str, grantee_kind, identifier: str | None) -> None`**
   - argv: `["share-folder", "<sf_uid>", "-a", "revoke", ...]`.
9. **`_share_record_to_shared_folder(self, *, shared_folder_uid: str, record_uid: str, can_edit: bool, can_share: bool) -> None`**
   - argv: `["share-folder", "<sf_uid>", "-a", "grant", "-r", record_uid, ...]`.
10. **`_set_shared_folder_default_record_share(self, *, shared_folder_uid: str, can_edit: bool, can_share: bool) -> None`**
    - argv: `["share-folder", "<sf_uid>", "-a", "grant", "--default-record", ...]`.
11. **`_discover_shared_folder_acl(self, *, shared_folder_uid: str) -> dict`**
    - argv: `["get", shared_folder_uid, "--format", "json"]`. Parse output → return `{"users": [...], "teams": [...], "records": [...], "default": {...}}`. Cite Commander's `get` JSON shape.

## NOT in scope for V7b

- Wiring these into `apply_plan` for sharing Change rows. (Defer to 7h-43 V7e or merge into V7a if V7a ends up needing the apply path.)
- Modifying `discover()` to return sibling rows. (The diff helpers accept `live_*` kwargs separately; threading through `discover()` is V7c+.)

## Tests — `tests/test_commander_cli_sharing.py` (NEW; ~18 cases)

For each method 1-11, write a stubbed `_run_cmd` test:

12. Patch `_run_cmd` to record argv. Call method. Assert exact argv list.
13. Test optional flag presence (`color`, `manage_users`, etc.).
14. Test parser-required flag combinations (e.g. `share-folder` requires `-a` action).
15. For `_discover_shared_folder_acl`: patch `_run_cmd` to return canned JSON; assert parsed dict shape.
16. Test ValueError raises on contradictory inputs (e.g. `grantee_kind="default"` with non-None `identifier`).

## Workflow

1. Read all listed files (especially Commander parsers — cite their line numbers in commit body).
2. Implement methods one-by-one with their stubbed test alongside.
3. `python3 -m ruff format <files> && python3 -m ruff check keeper_sdk tests`. Fix.
4. Full suite: `python3 -m pytest -q --no-cov`. Baseline 663+1; target +18 → 681+1.
5. `python3 -m pytest -q --cov=keeper_sdk --cov-fail-under=85`. Must stay above 85.
6. `python3 -m mypy keeper_sdk/providers/commander_cli.py tests/test_commander_cli_sharing.py`. Clean.
7. `git add -A && git commit -m "feat(sharing-v1): CommanderCliProvider sharing methods (stubbed)"`.
8. `git push -u origin cursor/sharing-cli-provider`.
9. Output `DONE: cursor/sharing-cli-provider <sha>` or `FAIL: <one-line>`.

## Constraints

- Caveman-ultra commit body; CITE Commander parser line:numbers for each method.
- No live tenant.
- Marker manager UNTOUCHED.
- Do not modify `keeper_sdk/providers/mock.py` (V7a territory).
- Do not modify `keeper_sdk/core/sharing_diff.py` or `sharing_models.py`.
- Do not modify `keeper_sdk/core/manifest.py` or `keeper_sdk/cli/main.py` (V7c territory).
- Methods are STUBBED for now — they make the `_run_cmd` calls but no Change-row dispatch.

# Anti-patterns to avoid (LESSONS-derived)

- LESSON `[orchestration][parallel-write-3way-conflict-pattern]` — strict file boundary, only `commander_cli.py` + new test file.
- LESSON `[capability-census][three-gates]` — V7b closes provider parity for sharing.v1 (alongside V7a). Schema status bump still gated on V8/V9.
- LESSON `[sprint][offline-write-fanout-3way-replication]` — branch from same SHA; only stub-tests, no live tenant; merge zone is `commander_cli.py` only — V7a is `mock.py` only — V7c is `manifest.py + cli/main.py` only. No overlap.
