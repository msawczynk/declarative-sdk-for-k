#!/usr/bin/env bash
# Offline Codex worker: workspace-write, no network. Parent supplies full prompt.
# Usage: CODEX_MODEL=gpt-5.5 scripts/agent/codex_offline_slice.sh path/to/prompt.md
# Prompt should include task, file scope, allowed commands, and DONE block from
# .github/codex/prompts/scoped-task.md — see docs/CODEX_CLI.md
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 PROMPT.md" >&2
  echo "  PROMPT.md must contain the complete Codex instructions (task + scope + DONE contract)." >&2
  exit 64
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROMPT_FILE="$1"

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "not a file: $PROMPT_FILE" >&2
  exit 66
fi

CODEX_MODEL="${CODEX_MODEL:-gpt-5.5}"
if [[ -n "${CODEX_BIN:-}" ]]; then
  _codex="$CODEX_BIN"
elif command -v codex >/dev/null 2>&1; then
  _codex="$(command -v codex)"
else
  echo "codex not found. Install Codex CLI or set CODEX_BIN (see docs/CODEX_CLI.md)." >&2
  exit 69
fi

if [[ ! -x "$_codex" && ! -f "$_codex" ]]; then
  echo "codex binary missing or not executable: $_codex" >&2
  exit 69
fi

exec "$_codex" exec \
  --skip-git-repo-check \
  --ephemeral \
  --model "$CODEX_MODEL" \
  -c approval_policy=never \
  --sandbox workspace-write \
  -C "$ROOT" \
  - < "$PROMPT_FILE"
