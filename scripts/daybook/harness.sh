#!/usr/bin/env bash
# Entry from dsk root: forwards to workspace-global daybook scripts.
# Does NOT vendor the harness; does NOT keep JOURNAL/LESSONS in this repo.
set -euo pipefail

ROOT="${DAYBOOK_SYNC_ROOT:-${HOME}/.cursor-daybook-sync}/scripts"
if [[ ! -d "$ROOT" ]]; then
  echo "daybook harness: missing directory: $ROOT" >&2
  echo "Set DAYBOOK_SYNC_ROOT to your cursor-daybook-sync clone, or install scripts there." >&2
  exit 1
fi

print_help() {
  cat <<'EOF'
dsk daybook harness — forwards to ~/.cursor-daybook-sync/scripts (or DAYBOOK_SYNC_ROOT).
Canonical JOURNAL/LESSONS: ~/Downloads/JOURNAL.md and ~/Downloads/LESSONS.md (not in this repo).

  bash scripts/daybook/harness.sh boot            # session boot
  bash scripts/daybook/harness.sh pre-claim        # before done/gate-lift claim
  bash scripts/daybook/harness.sh sync             # daybook → GitHub mirror
  bash scripts/daybook/harness.sh cost-check       # tier/cost probe
  bash scripts/daybook/harness.sh ksm-preflight     # before Commander login
  bash scripts/daybook/harness.sh harvest          # subagent_harvest (after workers)
  bash scripts/daybook/harness.sh distill-check     # JOURNAL bloat / stale sprint check
  bash scripts/daybook/harness.sh review-loop       # write hooks-log review digest
  bash scripts/daybook/harness.sh print-env         # print export lines (Downloads JOURNAL)
  bash scripts/daybook/harness.sh append JOURNAL '…one line…'
  bash scripts/daybook/harness.sh append LESSONS '…one line…'

Run daybook steps in a separate step from dsk product commits (no mixed batches).
Environment: DAYBOOK_SYNC_ROOT — daybook script repo (default: ~/.cursor-daybook-sync).
EOF
}

print_env() {
  # Matches agent_session_boot: default JOURNAL/LESSONS under $HOME/Downloads.
  printf 'export JOURNAL_PATH="${JOURNAL_PATH:-%s/Downloads/JOURNAL.md}"\n' "$HOME"
  printf 'export LESSONS_PATH="${LESSONS_PATH:-%s/Downloads/LESSONS.md}"\n' "$HOME"
  printf 'export DAYBOOK_REPO="${DAYBOOK_REPO:-%s/.cursor-daybook-sync}"\n' "$HOME"
  echo "# source these before: append, sync, daybook_append"
}

case "${1:-}" in
  "" | help | --help | -h)
    print_help
    exit 0
    ;;
  print-env)
    print_env
    exit 0
    ;;
esac

cmd="$1"
shift

case "$cmd" in
  boot) exec bash "$ROOT/agent_session_boot.sh" "$@" ;;
  pre-claim) exec bash "$ROOT/agent_pre_claim.sh" "$@" ;;
  sync) exec bash "$ROOT/sync_daybook.sh" "$@" ;;
  cost-check) exec bash "$ROOT/cost_check_now.sh" "$@" ;;
  ksm-preflight) exec bash "$ROOT/ksm_login_preflight.sh" "$@" ;;
  harvest) exec bash "$ROOT/subagent_harvest.sh" "$@" ;;
  distill-check) exec bash "$ROOT/agent_distill_check.sh" "$@" ;;
  review-loop) exec bash "$ROOT/agent_review_loop.sh" "$@" ;;
  append)
    kind="${1:-}"
    shift || true
    if [[ -z "$kind" || $# -lt 1 ]]; then
      echo "usage: $0 append JOURNAL|LESSONS '<one line>'" >&2
      exit 1
    fi
    # shellcheck disable=SC2048,SC2086
    exec bash "$ROOT/daybook_append.sh" "$kind" "$*"
    ;;
  *)
    echo "unknown: $cmd (use: $0 help)" >&2
    exit 1
    ;;
esac
