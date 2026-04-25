# `keeper_sdk/auth/` — login helper contract

Pluggable login. Default is `EnvLoginHelper` (env-var driven). Custom helpers
opt in via `KEEPER_SDK_LOGIN_HELPER=/abs/path/helper.py`.

## Modules

| File | LOC | Role |
|---|---:|---|
| `__init__.py` | 43 | Exports `EnvLoginHelper`, helper-loader, helper-protocol. |
| `helper.py` | 293 | `EnvLoginHelper` reads `KEEPER_EMAIL`/`KEEPER_PASSWORD`/`KEEPER_TOTP_SECRET` (+ optional `KEEPER_SERVER`/`KEEPER_CONFIG`). Implements Commander `LoginUi` contract: TOTP from base32 secret, device-approval prompts handled. Also: helper loader (`load_login_helper`) that imports a user-supplied helper file and wires its callable into `KeeperParams`. |

## Helper contract

A custom helper file at `KEEPER_SDK_LOGIN_HELPER` MUST expose:

```python
def get_keeper_params(*, server: str | None = None, config_path: str | None = None) -> KeeperParams: ...
```

Receives optional overrides; returns an authenticated `keepercommander.params.KeeperParams`.
30-line skeleton in `docs/LOGIN.md`.

## Where to land new work

| Change | File |
|---|---|
| New env-var fallback | `helper.py` `EnvLoginHelper.__init__` |
| New helper-loader behaviour | `helper.py::load_login_helper` |
| New auth backend (e.g. KSM-pull, OIDC) | new helper file referenced by `KEEPER_SDK_LOGIN_HELPER` (out-of-tree) — keep `auth/` minimal |

## Hard rules

- Never log password / TOTP secret / config path contents.
- `KEEPER_TOTP_SECRET` is the **base32 secret**, NOT a 6-digit code (documented; common confusion).
- Helper protocol: pure function returning `KeeperParams`. No side effects on import.
- Tests use `tests/test_auth_helper.py` mocks; never network.

## Reconciliation vs design

| Requirement | Status | Evidence |
|---|---|---|
| `EnvLoginHelper` shipped as in-tree reference | shipped | `helper.py`, `tests/test_auth_helper.py` |
| `KEEPER_SDK_LOGIN_HELPER` optional (env-var fallback) | shipped | `helper.py::load_login_helper` |
| Live smoke proved login contract via `--login-helper env` | shipped (2026-04-25) | `scripts/smoke/smoke.py`, `V1_GA_CHECKLIST.md` row 4 |
| End-to-end apply session refresh | DEFERRED | separate Commander-CLI gap, see `AUDIT.md` |
