# `.github/` — automation root

CI workflows + release workflow. Codex / agent orchestration scaffolding
(prompt templates, issue forms, manual Codex Action runner) is
operator-side infrastructure in the maintainer's private daybook
(`msawczynk/cursor-daybook`: `templates/github/`); not shipped from this
repo.

## Files

| Path | Role |
|---|---|
| `workflows/ci.yml` | CI: ruff + mypy + pytest 3.11/3.12/3.13 + examples job + drift-check (against upstream Commander) + build + `twine check`. Required for merge. |
| `workflows/publish.yml` | `on: release: published` → builds `dist/*`, runs `twine check`, uploads to GitHub Release via `gh release upload`. **No PyPI** publish. |

## Where to land new work

| Change | File |
|---|---|
| New CI gate | `workflows/ci.yml` |
| New release artifact / step | `workflows/publish.yml` + `docs/RELEASING.md` |

## Hard rules

- Publish workflow MUST `twine check dist/*` before upload; failure
  aborts release.
- Drift-check job pulls upstream Commander at `.commander-pin` SHA —
  keep that file accurate.

## Reconciliation

| Requirement | Status |
|---|---|
| CI matrix 3.11/3.12/3.13 | shipped |
| First green CI run on `main` | shipped (`fb6fb8b`) |
| GitHub Release asset workflow | shipped (`publish.yml`) |
| No PyPI distribution | by policy — `pyproject.toml` packaged for git/wheel install only |
| In-tree Codex Action / issue template | removed 2026-04-26; lives canonically in private daybook `templates/github/` (operator-side only). |
