# Codex slice prompts (parallel)

`00-ping.prompt.md` is a no-edit connectivity check (`codex exec` only).

Each other `*.prompt.md` is a **full** Codex instruction file (task + hard scope +
allowed commands + risks). Run one:

```bash
export CODEX_MODEL=gpt-5.5
scripts/agent/codex_offline_slice.sh scripts/agent/prompts/01-github-doc.prompt.md
```

Run **disjoint** slices in parallel (`00-ping` skipped unless `INCLUDE_PING=1`):

```bash
MAX_CODEX_JOBS=3 scripts/agent/run_parallel_codex.sh
```

End every prompt with the DONE block from `.github/codex/prompts/scoped-task.md`.

Do not commit `.codex-runs/` (gitignored).
