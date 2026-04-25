# Slice 01 — GitHub scaffolding + Codex GitHub doc

You are working on `declarative-sdk-for-k`.

## Task

Keep `.github/workflows/codex-task.yml`, `.github/ISSUE_TEMPLATE/codex_task.yml`, and `docs/CODEX_GITHUB.md` internally consistent: workflow_dispatch input names and issue-template fields should match what the doc describes. Fix only clear errors (YAML syntax, broken links to paths that exist, heading typos).

## Scope (hard boundary)

Edit **only** files under:

- `.github/`
- `docs/CODEX_GITHUB.md`

Do not touch `keeper_sdk/`, `tests/`, `scripts/smoke/`, or other docs.

## Success criteria

- `python3 -c "import pathlib,yaml; [yaml.safe_load(open(p,encoding='utf-8')) for p in pathlib.Path('.github/workflows').glob('*.yml')]"` succeeds from repo root.
- `docs/CODEX_GITHUB.md` links only to repo paths that exist on disk.

## Allowed commands

```bash
python3 -c "import pathlib,yaml; [yaml.safe_load(open(p,encoding='utf-8')) for p in pathlib.Path('.github/workflows').glob('*.yml')]"
bash -n .github/workflows/codex-task.yml 2>/dev/null || true
```

No `keeper`, no tenant, no `pytest` unless you add a test file inside `.github/` (prefer not).

## Final response

Use the DONE block from `.github/codex/prompts/scoped-task.md` (same repo).

```text
DONE
CHG: <files changed>
tests: <commands or none>
risks: <...>
TOKEN: clean | finding=<one-line>
```
