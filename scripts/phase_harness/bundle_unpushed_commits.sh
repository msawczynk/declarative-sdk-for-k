#!/usr/bin/env bash
# Pack local commits on `main` that are not on `origin/main` into a git bundle
# (for handoff to a machine with GitHub write access when `git push` is unavailable here).
# Usage: bundle_unpushed_commits.sh [OUTPUT_BUNDLE]
#   OUTPUT_BUNDLE defaults to /tmp/declarative-sdk-unpushed.bundle
# On the receiving clone (at the same `origin/main` as this machine had when the bundle
# was created):  git pull /path/to/bundle main  &&  git push origin main
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
OUT="${1:-/tmp/declarative-sdk-unpushed.bundle}"
if ! git rev-parse --verify origin/main >/dev/null 2>&1; then
  echo "error: need origin/main — run: git fetch origin" >&2
  exit 1
fi
if ! git rev-parse --verify main >/dev/null 2>&1; then
  echo "error: need branch main" >&2
  exit 1
fi
AHEAD="$(git rev-list --count origin/main..main 2>/dev/null || echo 0)"
if [[ "$AHEAD" -eq 0 ]]; then
  echo "Nothing to bundle (main is not ahead of origin/main)."
  exit 0
fi
# shellcheck disable=SC2016
git bundle create "$OUT" origin/main..main
echo "Created $AHEAD commit(s) in: $OUT"
git bundle verify "$OUT"
echo "On a clone whose origin/main matches this machine at bundle time:"
echo "  git pull $OUT main && git push origin main"
