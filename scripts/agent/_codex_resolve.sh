#!/usr/bin/env bash
# Print path to Codex CLI: CODEX_BIN env, else PATH, else newest Cursor extension bundle.
set -euo pipefail

if [[ -n "${CODEX_BIN:-}" ]]; then
  printf '%s\n' "$CODEX_BIN"
  exit 0
fi
if command -v codex >/dev/null 2>&1; then
  command -v codex
  exit 0
fi

shopt -s nullglob
candidates=( "$HOME/.cursor/extensions"/openai.chatgpt-*/bin/macos-aarch64/codex )
shopt -u nullglob
if [[ ${#candidates[@]} -eq 0 ]]; then
  exit 1
fi
# Prefer most recently modified binary (newest Cursor bundle).
ls -t "${candidates[@]}" | head -1
