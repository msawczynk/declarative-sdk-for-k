# Sprint Memo Scaffold

Use this policy when archiving Codex sprint artifacts.

- Preserve every `*.prompt.md` file byte-for-byte.
- Do not commit large raw Codex logs. Raw logs <=200 lines + DONE line; full logs available in `/tmp/` for ~7 days post-sprint.
- For larger `codex-*.log` files, archive a `.log.compact` file containing the first 30 lines of Codex preamble plus the last 200 lines of final output.
- Add an `INDEX.md` in the sprint directory listing each artifact, codex slug, marker state, DONE/FAIL evidence, and original-to-compact size.
- Keep each sprint memo directory under 2 MB unless an operator explicitly approves a larger archive.

