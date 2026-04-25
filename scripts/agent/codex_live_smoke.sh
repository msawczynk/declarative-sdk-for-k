#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 SCENARIO [extra smoke args...]" >&2
  exit 64
fi

SCENARIO="$1"
shift

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
_RESOLVER="$ROOT/scripts/agent/_codex_resolve.sh"
if [[ -z "${CODEX_BIN:-}" ]]; then
  CODEX_BIN="$(bash "$_RESOLVER")" || {
    echo "codex not found — set CODEX_BIN or install Cursor ChatGPT extension (see docs/CODEX_CLI.md)." >&2
    exit 69
  }
fi
CODEX_MODEL="${CODEX_MODEL:-gpt-5.5}"
LAB_DIR="${LAB_DIR:-/Users/martin/Downloads/Cursor tests/keeper-vault-rbi-pam-testenv}"
SMOKE_ENV="${CODEX_SMOKE_ENV:-}"

case "$SCENARIO" in
  pamUserNestedRotation)
    SMOKE_ENV="${SMOKE_ENV:-DSK_PREVIEW=1 DSK_EXPERIMENTAL_ROTATION_APPLY=1}"
    ;;
esac

SMOKE_COMMAND="${SMOKE_ENV:+$SMOKE_ENV }python3 scripts/smoke/smoke.py --login-helper env --scenario ${SCENARIO} $*"

if [[ ! -x "$CODEX_BIN" ]]; then
  echo "codex binary not executable: $CODEX_BIN" >&2
  exit 69
fi

exec "$CODEX_BIN" exec \
  --skip-git-repo-check \
  --ephemeral \
  --model "$CODEX_MODEL" \
  -c approval_policy=never \
  -c sandbox_workspace_write.network_access=true \
  --sandbox workspace-write \
  -C "$ROOT" \
  --add-dir "$LAB_DIR" \
  - <<EOF
Task: run one committed Keeper live-smoke harness command and report sanitized evidence only.

This is a smoke-only worker. Do not read or print private orchestration notes, preamble files, repo docs,
credential files, config files, env dumps, or secret-bearing logs. The safety
rules needed for this task are fully in this prompt.

Allowed command from repo root:
${SMOKE_COMMAND}

Rules:
- Do not run any other Keeper mutation command.
- Do not inspect or print credential/config/env file contents.
- Do not print env values or secrets.
- If command fails, report sanitized stdout/stderr tails already emitted by harness.
- Retry at most once, only for clear transient auth/session expiry, and say why.

Return compact LIVE_DONE with command, exit code, PASS/FAIL, sanitized evidence, caveats, TOKEN.
EOF
