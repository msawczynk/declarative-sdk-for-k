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
  # Internal-derived families — never publish
  "keeper_sdk/core/models_nhi.py"
  "keeper_sdk/core/models_ai_agent.py"
  "keeper_sdk/core/models_pam_extended.py"
  "keeper_sdk/core/pam_extended_diff.py"
  "keeper_sdk/core/schemas/nhi-agent"
  "keeper_sdk/core/schemas/ai-agent"
  "keeper_sdk/core/schemas/pam-extended"
  "keeper_sdk/core/schemas/keeper-pam-extended"
  "keeper_sdk/core/schemas/pam_extended"
  "docs/NHI_AI_AGENT_DESIGN.md"
  "docs/live-proof/keeper-pam-extended.v1.6574827c.wave8-live-b.sanitized.json"
  "tests/test_nhi_ai_agent_schema.py"
  "tests/test_pam_extended_schema.py"
  "tests/test_pam_extended.py"
  "tests/test_pam_extended_plan.py"
  "tests/test_keeper_pam_extended_schema.py"
  "tests/fixtures/examples/pam-extended"
  # KeeperDrive is in PR #1975 which is not in Commander 17.2.16.
  # Ship private-only until merged upstream and present in a released Commander.
  "keeper_sdk/core/_private_families.py"
  "keeper_sdk/core/models_keeper_drive.py"
  "keeper_sdk/core/schemas/keeper-drive"
  "docs/VERIFY_IMPLEMENT_TRUTH_TABLE.md"
  "tests/test_keeper_drive_schema.py"
  "tests/fixtures/examples/keeper-drive"
  # Upstream-gap design docs — never public
  "docs/NHI_AI_AGENT_DESIGN.md"
  "docs/MSP_FAMILY_DESIGN.md"
  "docs/LIVE_PROOF_LOG.md"
  # Operator DA plan (replace with generated CAPABILITY_STATUS.md for public)
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

echo "==> publish: generating public capability status doc"
bash scripts/generate_public_docs.sh

echo "==> publish: running pre-publish content check"
bash scripts/check_public_content.sh

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
