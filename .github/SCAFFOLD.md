# `.github/` — automation root

Issue forms, Codex prompt scaffolding, CI workflows.

## Files

| Path | Role |
|---|---|
| `ISSUE_TEMPLATE/codex_task.yml` | Task / scope / success packet for hands-off Codex workers (GitHub Action). Fields: task, hard scope, success criteria, allowed commands, live access policy, required DONE output. |
| `codex/prompts/scoped-task.md` | Reusable scoped-task template + DONE contract. Local Codex CLI prompts (`scripts/agent/prompts/*.prompt.md`) end with this DONE block. |
| `workflows/ci.yml` | CI: ruff + mypy + pytest 3.11/3.12/3.13 + examples job + drift-check (against upstream Commander) + build + `twine check`. Required for merge. |
| `workflows/codex-task.yml` | Manual `workflow_dispatch` Codex Action runner. Permissions `contents: read`. Uploads output + patch artifacts. Parent applies + reviews locally — never auto-push to `main`. |
| `workflows/publish.yml` | `on: release: published` → builds `dist/*`, runs `twine check`, uploads to GitHub Release via `gh release upload`. **No PyPI** publish. |

## Where to land new work

| Change | File |
|---|---|
| New CI gate | `workflows/ci.yml` |
| New Codex prompt template | `codex/prompts/<name>.md` |
| New release artifact / step | `workflows/publish.yml` + `docs/RELEASING.md` |
| New issue form | `ISSUE_TEMPLATE/<name>.yml` |

## Hard rules

- Codex Action: `contents: read` only. Patches via artifact, never push.
- `OPENAI_API_KEY` (Codex Action) configured at repo level only — never echo in logs.
- Publish workflow MUST `twine check dist/*` before upload; failure aborts release.
- Drift-check job pulls upstream Commander at `.commander-pin` SHA — keep that file accurate.

## Reconciliation

| Requirement | Status |
|---|---|
| CI matrix 3.11/3.12/3.13 | shipped |
| First green CI run on `main` | shipped (`fb6fb8b`) |
| GitHub Release asset workflow | shipped (`publish.yml`) |
| No PyPI distribution | by policy — `pyproject.toml` packaged for git/wheel install only |
| Codex Action issue form | shipped (`codex_task.yml`) |
| Manual Codex Action workflow | shipped (`codex-task.yml`) |
