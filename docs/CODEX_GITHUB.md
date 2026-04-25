# Managing Codex Through GitHub

**Default for day-to-day work:** local **Codex CLI** (`codex exec`) with the patterns in [`docs/CODEX_CLI.md`](./CODEX_CLI.md) and `scripts/agent/codex_offline_slice.sh` — fast loop, no GitHub secret required for offline slices.

Use **this document** when a task is clear enough to hand off **without** a live operator on your machine, or when you want **artifacts** (`codex.patch`, Action logs) and **manual dispatch** on GitHub.

## Supported Paths

1. **Codex cloud from GitHub comments**
   - Enable the repository in Codex settings.
   - On a PR, use `@codex review` for review or `@codex <task>` for a cloud task.
   - Good for PR-context fixes and review follow-ups.

2. **Codex GitHub Action**
   - Add `OPENAI_API_KEY` as a GitHub secret.
   - Use `.github/workflows/codex-task.yml` for manual scoped tasks; it calls `openai/codex-action@v1`, captures `codex-output.md`, and uploads `codex.patch`.
   - Use a committed prompt file, for example `.github/codex/prompts/scoped-task.md`, when you later factor the inline workflow prompt.
   - Set the action `model` input to `gpt-5.5` when that model is available in the GitHub environment; otherwise use the newest available Codex model and record the fallback in the issue.
   - Good for repeatable review, migration, or release-prep jobs.

3. **GitHub issue as task packet**
   - Use the `Codex task` issue template.
   - The issue must include task, scope, success criteria, allowed commands, and live-access policy.
   - Parent reviews the result and owns support claims, live proof, release, and merge decisions.

## Recommended First Workflow

1. Create a `Codex task` issue.
2. Fill every field. Keep scope tight.
3. Start Codex from GitHub with `@codex` or run the `Codex Task` workflow manually after the `OPENAI_API_KEY` secret is configured.
4. Require Codex to return the `DONE` block from `.github/codex/prompts/scoped-task.md`.
5. Parent verifies diff and reruns focused tests before merging.

## Guardrails

- Do not allow arbitrary issue text to auto-mutate `main`.
- Restrict triggers to trusted users or manual dispatch.
- Live Keeper tasks must name one committed smoke command and must not expose env/config/secrets.
- Gate-lift decisions require parent-reviewed live smoke evidence.
- If a task needs broad repo context, split it before assigning it to Codex.

## Current Local Limitation

Some local shells may not have `gh` installed; use the GitHub UI or install/authenticate GitHub CLI before expecting issue/PR automation. In this workspace, `gh` was absent during the 2026-04-25 process audit. The repo remote is `https://github.com/msawczynk/declarative-sdk-for-k.git`; GitHub-side setup still needs either Codex cloud repository enablement or an `OPENAI_API_KEY` secret for `openai/codex-action@v1`.

Local `codex exec` runs in this workspace are confirmed on `gpt-5.5`; scripts should pass `--model gpt-5.5` explicitly so later default changes do not silently downgrade workers.
