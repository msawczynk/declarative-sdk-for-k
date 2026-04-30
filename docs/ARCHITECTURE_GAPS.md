# Architecture gaps — declarative-sdk-for-k

Known design limitations that would need to be addressed before adopting DSK
in a multi-operator or production Keeper deployment. Both are expected at this
stage of an SDK; the goal of this document is to ensure they are surfaced
honestly before any internal gate-lift.

---

## 1. No distributed apply lock

**Risk level:** HIGH for multi-operator deployments, LOW for single-operator/CI use.

**Description:**
DSK has no equivalent of Terraform's state lock. When two `dsk apply` processes
run concurrently against the same Keeper tenant:
- Both read the live state independently (no exclusive lock).
- Both compute their own plan delta.
- Both issue Commander mutations.
- Result: last-writer-wins, ownership markers may be written twice with different
  values, and the live tenant can end up in an undefined state that neither
  manifest accurately describes.

**Current workaround:**
- CI/CD pipelines are inherently serialised (one pipeline run at a time).
- Single-operator use cases are safe.
- Recommended convention: namespace `uid_ref` values per team/environment
  so apply scopes are disjoint.

**Remediation path (not yet implemented):**
Option A — Keeper record-based lock: create a well-known `pamConfiguration`
record named `dsk-apply-lock-<tenant>` with a custom field `locked_by` and
`locked_at`. Acquire via CAS update (read current → assert empty → write holder
identity). Release on apply completion or timeout. This requires `record_management.update_record`
and adds ~2 RTTs per apply.
Option B — External lock: Redis/DynamoDB/file-based lock managed outside Keeper
(appropriate if DSK is deployed inside an existing CI/CD platform that already
has a lock primitive).

**Keeper will ask about this:** "What prevents two SEs from running `dsk apply`
on the same tenant simultaneously?" — answer: convention + disjoint namespacing
today; record-based CAS lock is the production path.

---

## 2. Partial apply has no rollback

**Risk level:** MEDIUM. Commander mutations are individually atomic, but a
multi-resource apply that fails halfway leaves the tenant in a partially-converged
state.

**Description:**
`dsk apply` executes resources in dependency order. If resource N fails, resources
0..N-1 are already applied and N+1..M remain unapplied. DSK does not:
- Roll back already-applied mutations.
- Leave a "checkpoint" that the next apply can resume from.
- Mark failed resources so operators know what succeeded.

**Current behaviour:**
- The CLI prints which resources succeeded before the failure.
- Exit code 1 (unexpected error) or 5 (capability error) is returned.
- Re-running `dsk apply` after fixing the root cause is safe: already-applied
  resources detect their ownership marker and compute NOOP; only the failed
  resource and onwards are retried.

**Why re-run is safe (idempotency guarantee):**
DSK's plan/diff is deterministic. A clean re-run after fixing the root cause
converges correctly because:
1. Already-created resources have ownership markers → plan emits NOOP.
2. The failed resource has no marker → plan emits CREATE or UPDATE.
3. Resources after the failure have no markers → plan emits CREATE.

**Remediation path (not yet implemented):**
- Add a `--checkpoint-file <path>` flag that writes a JSON record of each
  resource's apply status (DONE/FAILED/PENDING) as apply proceeds.
- On re-run with the same checkpoint file, skip resources already marked DONE.
- This reduces re-run time and makes partial failure visible in CI artefacts.

**Keeper will ask about this:** "What happens if a gateway fails to provision
halfway through?" — answer: apply halts, successful resources are stable
(idempotent re-run skips them), operator fixes the root cause and re-runs.

---

## Summary

| Gap | Risk | Workaround | Remediation | Effort |
|---|---|---|---|---|
| No distributed lock | HIGH (multi-op) | Disjoint namespacing / serialised CI | Record-based CAS lock | ~2 days |
| No partial-apply rollback | MEDIUM | Idempotent re-run | Checkpoint file flag | ~1 day |

Both gaps are standard for v0/v1 declarative tooling. Terraform did not have
state locking until v0.9 (2017). The key difference from Terraform is that
DSK's ownership marker system makes idempotent re-runs robust without a
separate state file — which partially compensates for the lack of a checkpoint.
