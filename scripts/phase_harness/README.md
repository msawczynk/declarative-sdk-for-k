# Phase harness (orchestrator-facing)

The **orchestration harness** (YAML spec, Codex launch, preflight, JOURNAL draft) lives
**outside** this delivery repo: `~/.cursor-daybook-sync/scripts/phase_runner.sh`.
See root [`AGENTS.md`](../../AGENTS.md) **§ Where orchestration lives** and
**§ Phase runner harness** — this folder only provides **in-repo** gates + an example
spec for copy-paste.

**Daybook session loop (boot, `doctor`, sync, append) from a clone** — use
[`../daybook/README.md`](../daybook/README.md); keep daybook work **separate** from
product `git` commits in this tree.

| Artifact | Role |
|----------|------|
| [`run_local_gates.sh`](./run_local_gates.sh) | Single command: `ruff check` + `ruff format --check` + `mypy keeper_sdk` + `pytest` (use when not delegating a multi-step `phase_runner` phase). |
| [`phase-spec.dsk.example.yaml`](./phase-spec.dsk.example.yaml) | Valid `phase_runner` spec shape; `repo_root` must be your machine’s absolute path. |

## Quick: local merge stack (no harness)

```bash
cd /path/to/declarative-sdk-for-k
bash scripts/phase_harness/run_local_gates.sh
```

(Activate `.venv` first if you use one; the script sources `.venv/bin/activate` when present.)

## Quick: validate a phase spec (preflight, no worker)

```bash
bash ~/.cursor-daybook-sync/scripts/phase_runner.sh --no-launch /path/to/your-spec.yaml
```

## Full phase (Codex worker + parent gates)

```bash
bash ~/.cursor-daybook-sync/scripts/phase_runner.sh /path/to/your-spec.yaml
```

Options: `--dry-run`, `--author-spec outcome.md` (author YAML from markdown),
`--verify-spec` (verifier preflight) — see
`~/.cursor-daybook-sync/scripts/templates/phase_runner.README.md`.

## Sibling paths (e.g. testenv KSM)

Background Codex workers can see extra dirs via
`CODEX_OFFLINE_EXTRA_DIRS` / `CODEX_EXTRA_ADD_DIRS` (see phase runner README). Do not
commit lab secrets; keep KSM / Commander paths in env, not in YAML.
