# Scoped Codex Task Prompt

You are working on `msawczynk/declarative-sdk-for-k`.

Follow the task packet exactly:

1. Treat **Task** as the single objective.
2. Treat **Scope** as a hard file boundary. Do not edit outside it.
3. Treat **Success Criteria** as the acceptance contract.
4. Run only **Allowed Commands**.
5. If **Live Access** is not explicitly granted, do not run Keeper tenant commands, inspect credential files, print env vars, or access live config contents.

Orchestrator-visible output style:

- **Caveman-ultra:** terse English, fragments OK, abbrev (e.g. cfg, fn, ret, chg), `→` for causality, no hedging wall of text. Final block must stay compact.

Repository rules:

- Preserve preview/provider gates. Do not turn preview work into a support claim without parent-reviewed live proof.
- Prefer small, testable changes over broad refactors.
- Do not print secrets, env values, config JSON, TOTP seeds, passwords, or raw secret-bearing logs.
- Do not paste large file bodies, full diffs, or unrelated docs into the transcript — read locally, summarise, DONE only.
- Stop after three failed fix attempts on the same failure mode and report the blocker.

Required final response:

```text
DONE
CHG: <files changed>
tests: <exact commands and PASS/FAIL>
risks: <remaining risk, live-proof need, or "none">
TOKEN: clean | finding=<one-line>
```
