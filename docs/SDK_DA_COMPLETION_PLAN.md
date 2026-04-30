# DSK Capability Status — v2.1.0

This page is the authoritative public summary of capability status across all
manifest families. It classifies every modeled capability as **Supported**,
**Preview-gated**, or **Upstream-gap**.

See `docs/VALIDATION_STAGES.md` for exit codes and `docs/COMMANDER.md` for
the Commander dependency matrix.

---

## Supported today

Capabilities in this tier have offline and live proof. They are part of the
stable contract and covered by CI.

| Capability | Family | Notes |
|---|---|---|
| Gateway reference + config + PAM lifecycle | `pam-environment.v1` | Full validate / plan / diff / apply / import for gateway, pam_configuration, pamMachine, pamDatabase, pamDirectory, pamUser, pamRemoteBrowser |
| RBI (remote browser isolation) | `pam-environment.v1` | Create → clean post-apply re-plan → destroy smoke-passed. P3.1 readback buckets documented in `docs/COMMANDER.md`. |
| Vault login records | `keeper-vault.v1` | L1: validate / plan / diff / apply; field-level diff on `login.fields[]` |
| Shared folders + record shares | `keeper-vault-sharing.v1` | Idempotent create; live proof accepted (`shared_folder_create_count=1` confirmed) |
| KSM app create | `keeper-ksm.v1` | Commander `KSMCommand.add_new_v5_app` wired; ownership marker written on create |
| Enterprise info (read/validate/plan/diff) | `keeper-enterprise.v1` | Online validate/plan/diff via `enterprise-info` Commander surface; teams, roles, nodes discoverable |
| Compliance report | reports | Redacted JSON envelope; graceful empty-cache path; `--no-fail-on-empty` |
| Password report | reports | Redacted JSON envelope |
| Security audit report | reports | Redacted JSON envelope; `--record-details`, `--node` flags |
| KSM usage report | reports | Commander-unavailable fallback envelope; `--quiet`, `--json` |
| KSM inter-agent bus | `keeper-ksm.v1` (bus) | CAS acquire/release/publish/consume; `MockBusStore` for offline tests |
| DSK MCP server | — | stdio JSON-RPC; lifecycle, report, and bus tools |

---

## Preview-gated (partial support)

Capabilities in this tier have working discover/validate/plan paths but apply
is blocked by a missing Commander surface or a tenant configuration requirement.

| Capability | Family | Gate | What works | What is blocked |
|---|---|---|---|---|
| MSP managed-company lifecycle | `msp-environment.v1` | Tenant must have `msp_permits.allowed_mc_products` (MSP product permit) | Discover, validate, plan, diff | Apply: `apply_msp_plan` exits 5. Tenant-capability gap, not a Commander or DSK bug. Workaround: Keeper admin console. |
| Enterprise apply (roles/teams write) | `keeper-enterprise.v1` | Commander `enterprise-role-add` / `enterprise-team-add` surface review | Online validate/plan/diff | Mutating apply is read-only; Commander ACL restrictions. |
| KSM app lifecycle beyond create | `keeper-ksm.v1` | Commander programmatic surface for update/delete/token/share | App create | Token provisioning, record shares, app updates, app deletion → exit 5 with `next_action` |

---

## Upstream-gap (waiting on Commander / Keeper API)

Capabilities in this tier are modeled in the schema but require a Commander or
Keeper API surface that does not exist in the pinned version (`keepercommander>=17.2.16,<18`).
DSK exits 5 with a `next_action` string when these are attempted live.

| Gap | Impact | Upstream status |
|---|---|---|
| `pam rotation info --format=json` | Rotation scheduling cannot be read back programmatically | Not in Commander `17.x`; upstream backlog |
| Gateway create (`mode: create`) | `dsk apply` with `mode: create` gateways exits 5 | No `pam gateway create` equivalent in Commander; use admin console |
| JIT access, JIT projects | Manifest schema stub exists; no apply path | No Commander API available; v2.x roadmap |
| KSM token provisioning, record shares | `keeper-ksm.v1` apply emits exit 5 for these operations | No stable programmatic Commander surface |
| MSP apply (without tenant permit) | `apply_msp_plan` exits 5 when tenant lacks MSP permit | Tenant configuration required; not a Commander version issue |

---

## Version matrix

| Component | Version |
|---|---|
| DSK | v2.1.0 |
| Commander floor | `keepercommander>=17.2.16,<18` |
| Python | 3.11, 3.12, 3.13 (all CI-tested) |
| Public test suite | 1375 passing, 5 skipped, 1 xfailed by design |

