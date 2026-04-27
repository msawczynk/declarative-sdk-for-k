# Sprint 7h-43/44/45 Wave1 Codex Archive

Compaction method: each `codex-*.log` raw archive was replaced by a
`.log.compact` file containing the first 30 lines plus the last 200 lines.
All prompt files in this directory are unchanged.

| Artifact | Codex slug | Marker state | DONE/FAIL line | Size |
|---|---|---|---|---|
| `codex-live-w2-ksm.log.compact` | `cursor/ksm-l1` | no live marker found; DONE line present | `DONE: cursor/ksm-l1 4df566d2c05e2f1ece4420b55ce6ff93c180291a` | 572,326 B -> 9,907 B |
| `codex-offline-20260427-074035-55545.log.compact` | `cursor/cov-cli-tests-A` | DONE, EXIT_CODE=0 | `DONE: cursor/cov-cli-tests-A 9683c0058e796b5a612d4c2f65ab6fc05117799c` | 1,101,003 B -> 9,117 B |
| `codex-offline-20260427-074035-55560.log.compact` | `cursor/cov-cli-tests-B` | DONE, EXIT_CODE=0 | `DONE: cursor/cov-cli-tests-B 866d90990b3acf94688d77733586d26fe89e60f2` | 1,137,758 B -> 9,640 B |
| `codex-offline-20260427-074035-55576.log.compact` | `cursor/cov-cli-tests-C` | DONE, EXIT_CODE=0 | `DONE: cursor/cov-cli-tests-C 5f647b0` | 847,821 B -> 9,697 B |
| `codex-offline-20260427-074035-55594.log.compact` | `cursor/mypy-strict` | DONE, EXIT_CODE=0 | `DONE: cursor/mypy-strict f7cc3a8` | 685,904 B -> 8,845 B |
| `codex-offline-20260427-074035-55610.log.compact` | `cursor/examples-expand` | DONE, EXIT_CODE=0 | `DONE: cursor/examples-expand a5151a5` | 1,117,085 B -> 7,441 B |
| `codex-offline-20260427-074047-56099.log.compact` | `cursor/sharing-scenario` | DONE, EXIT_CODE=0 | `DONE: cursor/sharing-scenario 2650ae3` | 1,458,253 B -> 9,304 B |
| `codex-offline-20260427-074047-56115.log.compact` | `cursor/sharing-harness` | DONE, EXIT_CODE=0 | `DONE: cursor/sharing-harness 7ed7590d63a189fbac677f5c277827171e135eed` | 1,617,764 B -> 8,957 B |
| `codex-offline-20260427-074047-56131.log.compact` | `cursor/sharing-tests` | DONE, EXIT_CODE=0 | `DONE: cursor/sharing-tests b63a96416c6602dd6709a01c12d71a4663e3adc6` | 758,485 B -> 9,678 B |
| `codex-offline-20260427-074047-56147.log.compact` | `subagent-telemetry-codex-aware` | DONE, EXIT_CODE=0 | no DONE/FAIL line; final evidence: `MEMO: subagent-telemetry-codex-aware READY` | 121,873 B -> 11,688 B |
| `codex-offline-v8c-fix.log.compact` | `V8c-fix` | DONE, EXIT_CODE=0 | `DONE: V8c-fix 08eeaf8231239520a9b4217c1f79d2e3660c6494` | 807,583 B -> 9,786 B |

