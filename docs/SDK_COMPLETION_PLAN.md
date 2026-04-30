# DSK Roadmap and Completion Plan

## Current release: v2.1.0

Released 2026-04-30. See `CHANGELOG.md` for the full change list.

**Highlights:**
- KSM inter-agent bus (CAS protocol, `MockBusStore`)
- `dsk report ksm-usage` with `--quiet` flag and Commander-unavailable fallback
- KSM app create wired end-to-end (Commander + ownership marker)
- vault-sharing live proof accepted
- compliance-report `--no-fail-on-empty` graceful path
- 1375 tests passing (public mirror)
- Python 3.11, 3.12, 3.13 all CI-tested

---

## v2.x — active development

| Item | Status | Blocker |
|---|---|---|
| MSP managed-company apply | Blocked | Tenant must have `msp_permits.allowed_mc_products`; not a Commander version issue |
| Rotation scheduling (`rotation_settings`) | Blocked | `pam rotation info --format=json` not in Commander `17.x` upstream |
| Gateway create (`mode: create`) | Blocked | No Commander API surface |
| KSM token/share/update/delete | Upstream-gap | No stable programmatic Commander surface in `17.2.16` |
| Enterprise apply (role/team mutations) | In progress | Commander ACL restrictions; read-only surfaces available today |
| Additional live proof expansion | Ongoing | Per-family; see `docs/SDK_DA_COMPLETION_PLAN.md` |

---

## v3.0 — planned (no date set)

| Item | Notes |
|---|---|
| Breaking rename | `declarative_sdk_k` shim removed; `keeper_sdk` is the only package name |
| NHI / AI resource types | Conditional on Keeper API GA for these resource families |
| Full MSP apply | Pending tenant capability + Commander write surface confirmation |
| Full rotation scheduling | Pending `pam rotation info --format=json` in Commander upstream |

---

## Support classification

See [`docs/SDK_DA_COMPLETION_PLAN.md`](./SDK_DA_COMPLETION_PLAN.md) for the
three-tier classification (Supported / Preview-gated / Upstream-gap) of every
modeled capability.

