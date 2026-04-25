#!/usr/bin/env bash
# Run every registered live-smoke scenario sequentially; tee per-scenario logs.
# Usage (repo root):
#   scripts/agent/run_smoke_matrix.sh
#   scripts/agent/run_smoke_matrix.sh --login-helper env
# Logs: .smoke-runs/<UTC-timestamp>/<scenario>.log (gitignored)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

login="${SMOKE_LOGIN_HELPER:-deploy_watcher}"
if [[ "${1:-}" == "--login-helper" ]]; then
  login="${2:?value required after --login-helper}"
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="${ROOT}/.smoke-runs/${stamp}"
mkdir -p "$out"

default_scenarios=(pamMachine pamDatabase pamDirectory pamRemoteBrowser pamUserNested)

echo "== smoke matrix: log dir ${out} login_helper=${login} =="

for s in "${default_scenarios[@]}"; do
  echo "---- ${s} ----"
  if ! python3 -u scripts/smoke/smoke.py --scenario "$s" --login-helper "$login" --log-level INFO 2>&1 | tee "${out}/${s}.log"; then
    echo "FAILED: ${s} (see ${out}/${s}.log)" >&2
    exit 2
  fi
done

echo "---- pamUserNestedRotation (preview + experimental) ----"
if ! env DSK_PREVIEW=1 DSK_EXPERIMENTAL_ROTATION_APPLY=1 \
  python3 -u scripts/smoke/smoke.py --scenario pamUserNestedRotation --login-helper env --log-level INFO 2>&1 | tee "${out}/pamUserNestedRotation.log"; then
  echo "FAILED: pamUserNestedRotation (see ${out}/pamUserNestedRotation.log)" >&2
  exit 2
fi

echo "== smoke matrix: OK (all scenarios) =="
