#!/usr/bin/env bash
# One-shot merge-style gate: ruff (lint+format) + mypy + isort + pytest.
# Replaces the removed in-tree `scripts/agent/phase0_gates.sh` (see AGENTS.md).
# Safe for CI and local: no live tenant, no network by default.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
# Prefer project venv when present.
# shellcheck disable=SC1091
if [[ -f .venv/bin/activate ]]; then
  # shellcheck source=/dev/null
  . .venv/bin/activate
fi
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy keeper_sdk
python3 -m pytest -q
