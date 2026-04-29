# Gateway `mode: create` — design decision memo

**status: DECIDED 2026-04-29 — Option B current, Option A deferred to v2.0**

## Context

`gateway.mode: create` implies the SDK would stand up a new PAM gateway instead of only adopting one. Provisioning touches Commander (e.g. `pam gateway new`), token exchange, and an agent on the target host—so we need an explicit fork before implementation.

## Options

### A — SDK-owned provisioning

| Pros | Cons |
|------|------|
| Fully declarative; single `apply` pass | Interactive token exchange + agent install on target; hard to automate safely |

SDK calls Commander directly to create the gateway.

### B — Operator-scaffolded `reference_existing`

| Pros | Cons |
|------|------|
| Clear separation; works today; operator uses manual flow, Terraform, or Commander | Not fully declarative for net-new environments |

Operator creates the gateway; manifest sets `reference_existing: true` and the SDK manages config atop the existing gateway.

### C — Hybrid

| Pros | Cons |
|------|------|
| Declares intent (`mode: create`); operator runs emitted bootstrap on host; SDK can wait for registration | More moving parts than B; needs reliable “registered” detection |

SDK issues a one-time token and a bootstrap script; operator runs it on the target; apply continues after registration.

## Recommendation

**Decided:** Ship **B** as the supported path now: `reference_existing` is safe and proven. Defer **A** (SDK-owned provisioning) to **v2.0** — requires non-interactive, auditable agent install and token flow. Option **C** (hybrid bootstrap script) is a v1.3 stretch if operator demand justifies it.
