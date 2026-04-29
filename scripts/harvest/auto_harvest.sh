#!/usr/bin/env bash
# Auto-harvest Codex T0 marker outputs and optionally commit/push repo changes.
set -euo pipefail

REPO='/Users/martin/Downloads/Cursor tests/declarative-sdk-for-k'
LAST_FILE='/tmp/dsk-last-harvest.ts'
SUMMARY='/tmp/harvest-summary.txt'
GATE_FAIL='/tmp/harvest-gate-fail.txt'
RESULT='/tmp/harvest-result.txt'

last_harvest="$(cat "${LAST_FILE}" 2>/dev/null || echo 0)"
last_harvest="${last_harvest//[^0-9]/}"
last_harvest="${last_harvest:-0}"

mtime_sec() {
  if [[ "$(uname -s)" == Darwin ]]; then
    stat -f %m "$1"
  else
    stat -c %Y "$1"
  fi
}

: >"${SUMMARY}"
declare -a done_markers=()

shopt -s nullglob
for marker in /tmp/codex-offline-*.marker /tmp/codex-live-*.marker; do
  [[ -f "${marker}" ]] || continue
  m="$(mtime_sec "${marker}")"
  if (( m <= last_harvest )); then
    continue
  fi
  if ! grep -q '^STATE=DONE' "${marker}"; then
    continue
  fi
  if ! grep -q '^EXIT_CODE=0$' "${marker}"; then
    continue
  fi

  base="$(basename "${marker}" .marker)"
  done_markers+=("${base}")

  log="${marker%.marker}.log"
  {
    printf '%s\n' "=== ${base} ==="
    if [[ -f "${log}" ]]; then
      tail -30 "${log}" | awk '/^DONE/,0'
      tail -30 "${log}" | grep 'LESSONS_CANDIDATE:' || true
    else
      printf '%s\n' "(missing log: ${log})"
    fi
    printf '\n'
  } >>"${SUMMARY}"
done

cd "${REPO}" || exit 1

markers_processed="${#done_markers[@]}"
committed_sha="NOTHING"

if [[ -n "$(git status --short)" ]]; then
  python3 -m ruff format keeper_sdk/ --quiet

  py_rc=0
  pyout="$(python3 -m pytest -q --tb=line 2>&1)" || py_rc="$?"

  printf '%s\n' "${pyout}" | tail -8

  if [[ "${py_rc}" -ne 0 ]]; then
    printf '%s\n' "${pyout}" >"${GATE_FAIL}"
    printf 'HARVEST FAIL: gate rc=%s\n' "${py_rc}"
    exit 1
  fi

  passed="$(printf '%s\n' "${pyout}" | grep -oE '[0-9]+ passed' | tail -1 | awk '{print $1}')"
  skipped="$(printf '%s\n' "${pyout}" | grep -oE '[0-9]+ skipped' | tail -1 | awk '{print $1}')"
  passed="${passed:-0}"
  skipped="${skipped:-0}"

  marker_lines=""
  if (( ${#done_markers[@]} > 0 )); then
    marker_lines="$(printf '%s\n' "${done_markers[@]}")"
  else
    marker_lines="(none)"
  fi

  commit_msg="chore(harvest): auto-commit T0 worker results [$(date -u +%Y-%m-%d)]

Workers completed since last harvest:
${marker_lines}

Gates: ${passed} passed, ${skipped} skipped"

  git add -A
  if git diff --cached --quiet; then
    printf 'nothing to commit (empty index after add)\nexit_code=0\n' >"${RESULT}"
  else
    git commit -m "${commit_msg}"
    committed_sha="$(git rev-parse HEAD)"
    push_rc=0
    git push origin main || push_rc="$?"
    printf 'exit_code=%s\ncommit_sha=%s\n' "${push_rc}" "${committed_sha}" >"${RESULT}"
    if [[ "${push_rc}" -ne 0 ]]; then
      printf 'HARVEST FAIL: push rc=%s\n' "${push_rc}"
      exit 1
    fi
  fi
else
  printf 'nothing to commit\nexit_code=0\n' >"${RESULT}"
fi

date +%s >"${LAST_FILE}"
printf 'HARVEST OK: %s markers processed, committed %s\n' "${markers_processed}" "${committed_sha}"
