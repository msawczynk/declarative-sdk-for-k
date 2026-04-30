# `keeper_sdk/secrets/` — KSM integration

Optional extra: `pip install 'declarative-sdk-for-k[ksm]'` (`keeper_secrets_manager_core`). Importing without extras raises `CapabilityError` on first use with `next_action` to install.

## Modules

| File | Role |
|------|------|
| `bootstrap.py` | `bootstrap_ksm_application` — Commander-driven KSM app on-ramp for `dsk bootstrap-ksm`. |
| `ksm.py` | `KsmSecretStore`, `KsmLoginCreds`, `load_keeper_login_from_ksm` — used by `KsmLoginHelper` in `keeper_sdk/auth/helper.py`. |
| `bus.py` | Inter-agent KSM bus — preview-gated / sealed; see `docs/SDK_DA_COMPLETION_PLAN.md` Phase B. |

## Docs

- `docs/KSM_BOOTSTRAP.md` — operator flow for bootstrap command.
- `docs/KSM_INTEGRATION.md` — `KsmLoginHelper` + config probes.

## Rules

- Never log field values; callers own redaction (`keeper_sdk.core.redact` for known patterns).
- `core/` does not import this package; one-way: `auth` and CLI may import `secrets`.
