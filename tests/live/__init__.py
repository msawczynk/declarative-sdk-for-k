"""Live-tenant tests.

Skipped by default. To run: set KEEPER_LIVE_TENANT=1 + provide credentials
per docs/LIVE_TEST_RUNBOOK.md. CI runs these only on the `live-smoke`
workflow with explicit `LIVE=1` input.

Per docs/V2_DECISIONS.md Q4: each schema family graduates from
`scaffold-only` to `supported` only when a corresponding live test in
this directory has produced a sanitized proof transcript at the schema's
`x-keeper-live-proof.evidence` path.
"""
