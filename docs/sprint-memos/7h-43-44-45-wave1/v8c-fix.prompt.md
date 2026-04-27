# 7h-43 V8c-fix — adapt sharing-lifecycle tests to V8a contract

Worktree: cwd is the primary SDK repo (already on main with V8a/c merged).

Goal: patch `tests/test_smoke_sharing_lifecycle.py` to use the actual V8a SPEC API. V8c assumed `build_manifest`/`build_resources` attributes but V8a delivered `resources_factory` and `verifier`.

# V8a SPEC contract (verify by reading scripts/smoke/scenarios.py — VAULT_SHARING_LIFECYCLE)
- `spec.name == "vaultSharingLifecycle"` (string)
- `spec.family == "keeper-vault-sharing.v1"` (string)
- `spec.resources_factory(...) -> list[dict]` — builds payload
- `spec.verifier(records) -> None` — raises on missing components
- `spec.description: str | None`
- NO `build_manifest`, NO `build_resources` attrs.

# Hard requirements
1. Read `scripts/smoke/scenarios.py` to confirm the V8a public API in detail (the resources_factory signature, what it returns, what verifier expects).
2. Read `tests/test_smoke_sharing_lifecycle.py` (V8c).
3. Replace every `getattr(spec, "build_manifest", None) or getattr(spec, "build_resources", None)` with `spec.resources_factory`.
4. Update test bodies to match the actual factory return shape (list of dicts with `resource_type` keys vs. whatever V8c assumed).
5. If verifier signature differs (V8a takes `Sequence[Any]`), adjust test fixtures.
6. Iterate until all 11 tests pass: `python3 -m pytest -q --no-cov tests/test_smoke_sharing_lifecycle.py`.
7. ruff format + check; mypy.
8. Full suite green: `python3 -m pytest -q --no-cov` → 841 passed, 1 skipped target.
9. `git add -A && git commit -m "test(smoke): adapt sharing-lifecycle to V8a resources_factory API (7h-43 V8c-fix)"`.
10. `git push origin main` (you are on main; push direct).
11. Output `DONE: V8c-fix <sha>` or `FAIL: <one-line>`.

# Constraints
- ONLY edit `tests/test_smoke_sharing_lifecycle.py`.
- Do NOT modify `scripts/smoke/scenarios.py` or `smoke.py`.
- This is a test-side fix; production scaffolds are correct.
