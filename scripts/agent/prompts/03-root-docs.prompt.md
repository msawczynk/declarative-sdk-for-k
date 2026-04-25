# Slice 03 — Root + checklist docs (no DAYBOOK fiction)

You are working on `declarative-sdk-for-k`.

## Task

Remove or replace references to deleted `docs/DAYBOOK.md` across root docs. Point maintainers at `docs/ORCHESTRATION_PHASE0_PARALLEL.md` + global daybook methodology (private sync) instead where a “how we run agents” pointer is needed. Keep claims truthful: no PyPI, no unsupported rotation/RBI as GA.

## Scope (hard boundary)

Edit **only**:

- `AUDIT.md`
- `README.md`
- `SCAFFOLD.md`
- `V1_GA_CHECKLIST.md`
- `docs/LOGIN.md`

Do not edit `keeper_sdk/`, `tests/`, `scripts/`, `.github/`.

## Success criteria

- No broken markdown links to `docs/DAYBOOK.md`.
- `README.md` still states GitHub-only install if that was already true.

## Allowed commands

```bash
rg 'DAYBOOK' AUDIT.md README.md SCAFFOLD.md V1_GA_CHECKLIST.md docs/LOGIN.md || true
```

No pytest required for doc-only slice unless you want `python3 -m pytest -q tests/test_cli.py` as smoke (optional).

## Final response

DONE block per `.github/codex/prompts/scoped-task.md`.

```text
DONE
CHG: <files changed>
tests: <none or pytest line>
risks: <...>
TOKEN: clean | finding=<one-line>
```
