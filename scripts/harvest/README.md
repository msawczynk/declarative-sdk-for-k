# `auto_harvest.sh`

Scans `/tmp/codex-offline-*.marker` / `codex-live-*.marker` for `STATE=DONE` + `EXIT_CODE=0` newer than `/tmp/dsk-last-harvest.ts`; appends DONE blocks and `LESSONS_CANDIDATE` lines to `/tmp/harvest-summary.txt`; if repo dirty runs `python3 -m ruff format` + `python3 -m pytest`, then `git commit` + `git push origin main`; refreshes harvest timestamp on success.

```bash
bash "/Users/martin/Downloads/Cursor tests/declarative-sdk-for-k/scripts/harvest/auto_harvest.sh"
```
