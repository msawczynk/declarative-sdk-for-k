# 7h-45 V8a — vaultSharingLifecycle ScenarioSpec

Worktree: `/Users/martin/Downloads/Cursor tests/worktrees/cursor-sharing-scenario`, branch `cursor/sharing-scenario`, base 8044bb8.

Goal: append `vaultSharingLifecycle` `ScenarioSpec` to `scripts/smoke/scenarios.py`. Verifier function. Resource builder. NO harness wiring (V8b owns that). NO tests (V8c owns).

# Required reading
- `scripts/smoke/scenarios.py` full read (~400 LOC).
- `keeper_sdk/core/sharing_models.py` (V5a) for SharingManifestV1 shape.
- `keeper_sdk/core/sharing_diff.py` resource_type strings: `sharing_folder`, `sharing_shared_folder`, `sharing_record_share`, `sharing_share_folder`.
- `examples/sharing.example.yaml` (V7c) for shape reference.
- LESSON `[smoke][family-dispatch-vs-profile-orthogonality]` 7h-37.

# Hard requirements
1. EDIT `scripts/smoke/scenarios.py` (append only):
   - `def _sharing_lifecycle_resources(...) -> list[dict[str, Any]]`: builds 1 user_folder + 1 shared_folder + 1 record + 1 record_share + 1 share_folder (default share).
   - `def _verify_sharing_lifecycle(records: Sequence[Any]) -> None`: asserts the round-trip — folder marker present, shared_folder present, record_share grantee resolved, share_folder present.
   - `VAULT_SHARING_LIFECYCLE = ScenarioSpec(name="vaultSharingLifecycle", family="keeper-vault-sharing.v1", resources_factory=_sharing_lifecycle_resources, verifier=_verify_sharing_lifecycle)`.
2. Use string literal `"vaultSharingLifecycle"` for the scenario name (V8b will dispatch on this exact string).
3. Do NOT modify any other file. Do NOT touch `smoke.py`.

# Workflow
1. Read sources.
2. Append SPEC + helpers.
3. ruff format scripts/smoke/scenarios.py; ruff check.
4. mypy scripts/smoke/scenarios.py.
5. Full suite green (no behavior change for non-sharing paths).
6. `git add -A && git commit -m "feat(smoke): vaultSharingLifecycle ScenarioSpec (7h-45 V8a)"`.
7. `git push -u origin cursor/sharing-scenario`.
8. Output `DONE: cursor/sharing-scenario <sha>` or `FAIL: <one-line>`.

# Constraints
- Disjoint from V8b (`smoke.py` only) and V8c (`tests/test_smoke_sharing_lifecycle.py` only).
- Caveman commit body.
- The exact string `"vaultSharingLifecycle"` MUST be the SPEC name — V8b assumes it.
