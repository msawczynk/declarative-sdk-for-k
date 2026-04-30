#!/usr/bin/env bash
# publish.sh — push clean SDK release to the public mirror (declarative-sdk-for-k)
# Run from repo root. Requires 'public' remote to be set.
# Usage: bash scripts/publish.sh [--tag v2.x.x]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

TAG="${2:-}"
if [[ "${1:-}" == "--tag" ]]; then TAG="$2"; fi

echo "==> publish: preparing clean export"

# Files/dirs that must never reach the public repo
OPERATOR_EXCLUDES=(
  AUDIT.md
  REVIEW.md
  RECONCILIATION.md
  "docs/DSK_NEXT_WORK.md"
  "docs/SDK_DA_COMPLETION_PLAN.md"
  "docs/SDK_COMPLETION_PLAN.md"
  "docs/V2_DECISIONS.md"
  "docs/MSP_FAMILY_DESIGN.md"
  "scripts/rocky"
  "scripts/daybook"
  "scripts/dsk_orchestrator_loop.sh"
  "scripts/dsk_wave_next.sh"
  ".live-smoke"
  "CURSOR_PROMPT.md"
)

WORK_BRANCH="publish/$(date +%Y%m%d-%H%M%S)"
git fetch public
git checkout -b "$WORK_BRANCH" public/main 2>/dev/null || git checkout -b "$WORK_BRANCH"

# Overlay current main content
git checkout main -- .

# Strip operator files
for f in "${OPERATOR_EXCLUDES[@]}"; do
  if [[ -e "$f" ]]; then
    git rm -rf --cached "$f" 2>/dev/null || true
    rm -rf "$f"
  fi
done

# Ensure .gitignore covers operator paths
grep -q "AUDIT.md" .gitignore 2>/dev/null || cat >> .gitignore <<'GITIGNORE'

# Operator-private — never publish
AUDIT.md
REVIEW.md
RECONCILIATION.md
docs/DSK_NEXT_WORK.md
docs/SDK_DA_COMPLETION_PLAN.md
docs/SDK_COMPLETION_PLAN.md
docs/V2_DECISIONS.md
scripts/rocky/
scripts/daybook/
scripts/dsk_orchestrator_loop.sh
scripts/dsk_wave_next.sh
.live-smoke/
GITIGNORE

git add -A
git commit -m "release: clean SDK publish $(date +%Y-%m-%d)${TAG:+ $TAG}" || echo "nothing to commit"

echo "==> publish: pushing to public remote"
git push public "$WORK_BRANCH:main" --force-with-lease

if [[ -n "$TAG" ]]; then
  git tag "$TAG"
  git push public "$TAG"
  echo "==> publish: tagged $TAG on public"
fi

git checkout main
git branch -D "$WORK_BRANCH"
echo "==> publish: done. public mirror updated."
