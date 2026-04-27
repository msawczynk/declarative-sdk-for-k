<!-- Generated from templates/SPRINT_readonly-memo.md, version 2026-04-27 -->

## Sprint 7h-42 V7d — `keeper_sdk/core/sharing_diff.py` split review (codex readonly memo)

You are a codex CLI **readonly** worker. Sprint 7h-41 V6b grew `keeper_sdk/core/sharing_diff.py` from 365 LOC (folders only) to ~1300 LOC after the 3 sibling-block helpers landed. Single-file modules pass 1000 LOC are a refactor signal — but breaking up working code has its own costs (import churn, cross-test breakage, history fragmentation). The orchestrator wants a **decision memo** that says either:

- **HOLD** (don't split): file size is fine; cohesion outweighs LOC. Prove it by citing reading-flow patterns for similar `vault_diff.py` (~640 LOC, single file, no split planned).
- **SPLIT** (refactor): propose concrete file layout (e.g. `sharing_diff/__init__.py + folders.py + shared_folders.py + record_shares.py + share_folders.py`), import surface preservation, mypy/ruff/test impact prediction.

# Required reading

1. `keeper_sdk/core/sharing_diff.py` (current ~1300 LOC) — full read. Measure exactly: how many LOC are constants/dataclasses, how many are helpers per block, how many are the public `compute_sharing_diff` body.
2. `keeper_sdk/core/vault_diff.py` (~640 LOC after 7h-39 V1+V2+V3 merge) — comparison case. Was IT split? No, per current `main`. Why not? Cite the design intent.
3. `keeper_sdk/core/diff.py` — for comparison; PAM diff is even bigger (~291 stmts per pytest --cov). Cite its size + structure.
4. `keeper_sdk/core/sharing_models.py` (~229 LOC) — does it follow the same single-file shape? If yes, splitting `sharing_diff.py` while keeping `sharing_models.py` single creates an asymmetry to defend.
5. `tests/test_sharing_diff_*.py` (4 files: folders + 3 sibling blocks, ~12 cases each post-V6b) — do they import only `compute_sharing_diff` and helpers from one module? Count import statements.
6. LESSON `[orchestration][parallel-write-3way-conflict-pattern]` 7h-39 — splitting a frequently-edited file reduces parallel-write merge conflict surface. Quantify how often `sharing_diff.py` will be touched in 7h-42/43/44.
7. `git log --follow keeper_sdk/core/sharing_diff.py | head -30` — count touches in last 4 sprints (V5a, V6b, future V7+).

# Deliverable: ~120-line decision memo

## Section 1: Current state audit

- Measure `sharing_diff.py` LOC by section (constants, _Live* dataclasses, _* helpers per block, public function). Cite exact line ranges.
- Compare to `vault_diff.py`: section structure, total LOC, public surface.
- Compare to `diff.py` (PAM): how big is the equivalent module, structurally.
- Test import surface: which symbols do tests import from `sharing_diff`? Count each.

## Section 2: Cost-benefit analysis

- **Cost of HOLD**: future sprints (7h-43 + 7h-44) will add: live-proof transcript-aware diff hooks? unlikely. Smoke scenarios use diff but don't extend it. So `sharing_diff.py` is probably stable now. Validate.
- **Cost of SPLIT**: re-organize 1300 LOC into N files. Update imports in 4 test files + `manifest.py` + `cli/main.py`. Run mypy + ruff + full pytest. Risk: silent import-order regression, missed re-export.
- **Benefit of SPLIT**: parallel-write fan-out friendlier (7h-39 V1/V2/V3 had 3-way merge conflicts in the equivalent vault file). Reduced per-file LOC for code review.
- **Benefit of HOLD**: zero churn; test discovery stays trivial; git history stays linear.

## Section 3: Recommend HOLD vs SPLIT

State explicitly: `RECOMMEND: HOLD` or `RECOMMEND: SPLIT`. Justify in 3-5 sentences citing the audit.

## Section 4: If SPLIT — concrete refactor patch sketch

Provide:
- Proposed file layout with bullet-listed file purposes.
- `keeper_sdk/core/sharing_diff/__init__.py` re-export list (preserves the public API surface so test imports + manifest.py imports don't break).
- Migration script outline (a single `git mv` + multiple regex replaces) OR a manual diff outline.
- Estimated wall time for a write worker to land it (e.g. 4-6min based on V5a/V6b worker patterns).

## Section 5: If HOLD — alternate optimization

If recommending HOLD, propose ONE small refactor that captures most of the SPLIT's benefit without the churn (e.g. extracted constants module `sharing_diff_resource_types.py`, or grouped section markers `# region shared_folders`).

## Section 6: CANDIDATE LESSON

`2026-04-27 [refactor][threshold-driven-split-decision] <one-line on when to split a multi-block diff module>`.

# Constraints

- Read-only.
- Cite file:line for every LOC measurement.
- Output the full memo as your final response.
- Do not modify any files.
- If the audit reveals splitting would reduce future merge conflict surface significantly (e.g. >5 conflicts predicted in next 5 sprints), recommend SPLIT regardless of size.
