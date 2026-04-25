#!/usr/bin/env bash
# Non-agentic Phase 0 / merge gates for declarative-sdk-for-k.
# Usage: from repo root — scripts/agent/phase0_gates.sh quick|full
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

mode="${1:-quick}"
if [[ "$mode" != "quick" && "$mode" != "full" ]]; then
  echo "usage: $0 quick|full" >&2
  echo "  quick — focused pytest + ruff on hot paths + shell syntax" >&2
  echo "  full  — full pytest, repo-wide ruff + format, mypy, build+twine" >&2
  exit 64
fi

echo "== phase0_gates: $mode (cwd=$ROOT) =="

bash -n scripts/agent/codex_live_smoke.sh
bash -n scripts/agent/codex_offline_slice.sh
bash -n scripts/agent/phase0_gates.sh

if python3 -c "import yaml" 2>/dev/null; then
  for wf in .github/workflows/*.yml .github/workflows/*.yaml; do
    [[ -f "$wf" ]] || continue
    python3 -c "import sys,yaml; yaml.safe_load(open(sys.argv[1],encoding='utf-8'))" "$wf"
  done
  echo "OK: parsed workflow YAML under .github/workflows/"
else
  echo "skip: PyYAML not installed — pip install pyyaml or use dev extras to validate workflow YAML"
fi

if [[ "$mode" == "quick" ]]; then
  python3 -m pytest -q tests/test_cli.py tests/test_commander_cli.py tests/test_smoke_scenarios.py tests/test_smoke_args.py
  python3 -m ruff check keeper_sdk/cli/main.py keeper_sdk/providers/commander_cli.py tests/test_cli.py tests/test_commander_cli.py
else
  python3 -m pytest -q
  python3 -m ruff check .
  python3 -m ruff format --check .
  python3 -m mypy keeper_sdk
  rm -rf dist
  python3 -m build
  python3 -m twine check dist/*
fi

echo "== phase0_gates: OK =="
