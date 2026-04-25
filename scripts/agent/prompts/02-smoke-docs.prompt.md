# Slice 02 — Smoke harness docs vs scenarios

You are working on `declarative-sdk-for-k`.

## Task

Align `scripts/smoke/README.md` with `scripts/smoke/scenarios.py`: every scenario name documented as supported or experimental should exist in code; remove stale names; add one-line pointer to `docs/SDK_DA_COMPLETION_PLAN.md` Phase 0 for “not supported yet” items if missing.

## Scope (hard boundary)

Edit **only**:

- `scripts/smoke/README.md`
- `scripts/smoke/scenarios.py`

Do **not** edit `smoke.py`, `tests/`, or `keeper_sdk/` in this slice.

## Success criteria

- `python3 -m pytest -q tests/test_smoke_scenarios.py` passes.

## Allowed commands

```bash
python3 -m pytest -q tests/test_smoke_scenarios.py
```

No Keeper live commands.

## Final response

DONE block per `.github/codex/prompts/scoped-task.md`.

```text
DONE
CHG: <files changed>
tests: python3 -m pytest -q tests/test_smoke_scenarios.py → PASS/FAIL
risks: <...>
TOKEN: clean | finding=<one-line>
```
