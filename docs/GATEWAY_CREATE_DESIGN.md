# Gateway `mode: create` — design decision memo

**status: UPDATED 2026-04-30 — control-plane create wired; agent bootstrap still operator-owned**

## Context

`gateway.mode: create` now calls Commander `pam gateway new` through the
in-process `PAMCreateGatewayCommand`. This creates the Keeper control-plane
gateway and one-time initialization material. Installing/running the gateway
agent on the target host remains operator-owned.

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

**Updated:** DSK supports the Commander control-plane create path, while
`reference_existing` remains the safest path for already-provisioned gateways.
Full SDK-owned host bootstrap is still deferred until a non-interactive,
auditable agent install contract exists.
