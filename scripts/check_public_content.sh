#!/usr/bin/env bash
# check_public_content.sh — pre-publish content validator
#
# DESIGN: This script is called by publish.sh AFTER stripping OPERATOR_EXCLUDES
# from the publish work branch. It checks the stripped tree, not the full private repo.
# Running on the full private repo (main) will always fail Gate 1 — that is expected.
#
# Gate 1: stripped private .py modules must NOT be present in tree
# Gate 2: stripped private schema dirs must NOT be present in tree
# Gate 3: operator-only DA plan file must NOT be present in tree
# Gate 4: version consistency (warn only)
set -euo pipefail

FAIL=0

# --- Gate 1: stripped modules must NOT be present in tree ---
echo "==> check_public_content: Gate1 — verifying stripped .py modules absent"
STRIPPED_MODULE_FILES=(
  "keeper_sdk/core/models_nhi.py"
  "keeper_sdk/core/models_ai_agent.py"
  "keeper_sdk/core/models_pam_extended.py"
  "keeper_sdk/core/pam_extended_diff.py"
)
for f in "${STRIPPED_MODULE_FILES[@]}"; do
  if [[ -f "$f" ]]; then
    echo "ERROR [Gate1]: Stripped module still present: $f" >&2
    FAIL=1
  fi
done

# --- Gate 2: stripped schema dirs must NOT be present ---
echo "==> check_public_content: Gate2 — verifying stripped schema dirs absent"
STRIPPED_SCHEMA_DIRS=(
  "keeper_sdk/core/schemas/nhi-agent"
  "keeper_sdk/core/schemas/ai-agent"
  "keeper_sdk/core/schemas/pam-extended"
  "keeper_sdk/core/schemas/keeper-pam-extended"
)
for d in "${STRIPPED_SCHEMA_DIRS[@]}"; do
  if [[ -d "$d" ]]; then
    echo "ERROR [Gate2]: Stripped schema dir still present: $d" >&2
    FAIL=1
  fi
done

# --- Gate 3: operator DA plan must NOT be present ---
# SDK_DA_COMPLETION_PLAN.md is an internal operator document; public uses CAPABILITY_STATUS.md
echo "==> check_public_content: Gate3 — verifying operator DA plan excluded"
OPERATOR_ONLY_DOCS=(
  "docs/SDK_DA_COMPLETION_PLAN.md"
  "docs/DSK_NEXT_WORK.md"
  "docs/SDK_COMPLETION_PLAN.md"
  "docs/V2_DECISIONS.md"
  "docs/MSP_FAMILY_DESIGN.md"
  "docs/NHI_AI_AGENT_DESIGN.md"
  "AUDIT.md"
  "REVIEW.md"
)
for f in "${OPERATOR_ONLY_DOCS[@]}"; do
  if [[ -f "$f" ]]; then
    echo "ERROR [Gate3]: Operator-only doc still present: $f" >&2
    FAIL=1
  fi
done

# --- Gate 4: version consistency check (warn only) ---
echo "==> check_public_content: Gate4 — checking version consistency"
if [[ -f pyproject.toml && -f CHANGELOG.md ]]; then
  PYVER=$(grep -E '^version\s*=' pyproject.toml | head -1 | sed 's/.*=\s*"\(.*\)"/\1/')
  CLVER=$(grep -E '^\#\#\s*\[' CHANGELOG.md | head -1 | sed 's/.*\[\(.*\)\].*/\1/')
  if [[ -n "$PYVER" && -n "$CLVER" && "$PYVER" != "$CLVER" && "$CLVER" != "Unreleased" ]]; then
    echo "WARN [Gate4]: pyproject.toml version '$PYVER' != CHANGELOG.md latest '$CLVER'"
  fi
fi


# --- Gate 5: published docs must NOT contain private family name strings ---
echo "==> check_public_content: Gate5 — scanning published docs for private family refs"
PRIVATE_PATTERN="nhi-agent|nhi_agent|ai-agent|ai_agent|pam-extended|pam_extended|keeper-drive|keeperdrive"
PUBLIC_SCANNED_DOCS=(
  "README.md"
  "CHANGELOG.md"
  "docs/COMMANDER_COVERAGE.md"
  "docs/CAPABILITY_STATUS.md"
)
for f in "${PUBLIC_SCANNED_DOCS[@]}"; do
  if [[ -f "$f" ]]; then
    if grep -qiE "$PRIVATE_PATTERN" "$f"; then
      echo "ERROR [Gate5]: Private family reference found in published doc: $f" >&2
      grep -inE "$PRIVATE_PATTERN" "$f" | head -10 >&2
      FAIL=1
    fi
  fi
done

# --- Gate 6: scan Python source for private family refs (excluding known guarded stubs) ---
# manifest.py / __init__.py intentionally contain try/except fallback stubs (correct public-build guards)
# e.g. "except ImportError: FAMILY = \"ai-agent.v1\"" -- not a leak. __pycache__ .pyc also excluded.
GATE6_ALLOWLIST="keeper_sdk/core/manifest[.]py|keeper_sdk/core/__init__[.]py|keeper_sdk/core/schema[.]py|keeper_sdk/core/models_terraform[.]py|keeper_sdk/mcp/server[.]py|keeper_sdk/cli/main[.]py"
echo "==> check_public_content: Gate6 — scanning Python source for private refs (excl guarded stubs)"
if command -v rg &>/dev/null; then
  LEAKED=$(rg -l --glob '*.py' "$PRIVATE_PATTERN" keeper_sdk/ 2>/dev/null \
    | { grep -vE "$GATE6_ALLOWLIST" || true; } | head -5)
else
  LEAKED=$(grep -rlE "$PRIVATE_PATTERN" --include='*.py' keeper_sdk/ 2>/dev/null \
    | { grep -vE "$GATE6_ALLOWLIST" || true; } | head -5)
fi
if [[ -n "$LEAKED" ]]; then
  echo "ERROR [Gate6]: Private family ref outside guarded stubs:" >&2
  echo "$LEAKED" >&2
  FAIL=1
fi

if [[ $FAIL -eq 1 ]]; then
  echo ""
  echo "==> check_public_content: FAILED — run publish.sh to strip before checking," >&2
  echo "    or fix OPERATOR_EXCLUDES if running in publish work branch." >&2
  exit 1
fi

echo "==> check_public_content: PASSED (all gates)"
exit 0
