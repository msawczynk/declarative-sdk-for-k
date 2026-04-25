#!/usr/bin/env bash
# Run all scripts/agent/prompts/*.prompt.md through codex_offline_slice.sh in parallel.
# Logs: .codex-runs/<UTC>/*.log — review before merge; do not commit logs.
# Usage: MAX_CODEX_JOBS=2 CODEX_MODEL=gpt-5.5 scripts/agent/run_parallel_codex.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

RUN_DIR="${ROOT}/.codex-runs/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUN_DIR"
MAX="${MAX_CODEX_JOBS:-3}"

shopt -s nullglob
prompts=(scripts/agent/prompts/*.prompt.md)
shopt -u nullglob

if [[ ${#prompts[@]} -eq 0 ]]; then
  echo "no scripts/agent/prompts/*.prompt.md — add slice prompts first" >&2
  exit 66
fi

echo "logs -> $RUN_DIR (max concurrent: $MAX)"

run_one() {
  local p="$1"
  local base
  base="$(basename "$p" .prompt.md)"
  echo "start $base"
  if ! CODEX_MODEL="${CODEX_MODEL:-gpt-5.5}" "$ROOT/scripts/agent/codex_offline_slice.sh" "$p" >"$RUN_DIR/${base}.log" 2>&1; then
    echo "FAIL $base (see $RUN_DIR/${base}.log)" >&2
    return 1
  fi
  echo "ok $base"
}

idx=0
for p in "${prompts[@]}"; do
  while [[ "$(jobs -p 2>/dev/null | wc -l | tr -d ' ')" -ge $MAX ]]; do
    sleep 0.3
  done
  run_one "$p" &
  ((idx++)) || true
done
wait
echo "done — inspect logs under $RUN_DIR"
