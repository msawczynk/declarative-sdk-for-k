# Login helper contract

`dsk` needs a logged-in Commander `KeeperParams` for the two
subcommands that refuse to run cleanly in a subprocess: `pam project
import` and `pam project extend`. Everything else routes through
`keeper --batch-mode`.

## Two options

### 1. Built-in `EnvLoginHelper` (recommended for quickstarts + CI)

No code required. Set:

| Env var                  | Required | Notes                                          |
|--------------------------|----------|------------------------------------------------|
| `KEEPER_EMAIL`           | yes      |                                                |
| `KEEPER_PASSWORD`        | yes      |                                                |
| `KEEPER_TOTP_SECRET`     | yes      | base32 (the `secret=...` from the `otpauth://` URI), **not** a 6-digit code |
| `KEEPER_SERVER`          | no       | defaults to `keepersecurity.com`               |
| `KEEPER_CONFIG`          | no       | path to a Commander config JSON to warm        |

```bash
export KEEPER_EMAIL='you@example.com'
export KEEPER_PASSWORD='...'
export KEEPER_TOTP_SECRET='JBSWY3DPEHPK3PXP'
dsk --provider commander apply env.yaml
```

Under the hood `EnvLoginHelper`:

- imports `keepercommander` + `pyotp` lazily (so `dsk` still
  imports cleanly on machines without them),
- handles the TOTP edge-of-window race (sleeps into the next window
  when within 5 s of the boundary — see `LESSONS.md` 2026-04-23),
- auto-accepts device-approval prompts and answers two-factor
  challenges via TOTP.

If any of those behaviours are wrong for your environment, move to
option 2.

### 2. Custom helper via `KEEPER_SDK_LOGIN_HELPER`

Point the env var at **one Python file** that exposes either:

- module-level `load_keeper_creds()` and `keeper_login(...)`, **or**
- an instance named `helper` with the same two attributes.

#### Minimal skeleton (~30 lines)

```python
# /opt/dsk/my_login.py
from __future__ import annotations
from typing import Any


def load_keeper_creds() -> dict[str, str]:
    # Pull from wherever you trust: KSM, Vault, HSM, Boundary, etc.
    # Return the three required keys + any extras your keeper_login()
    # knows how to consume (the SDK passes the dict through as kwargs).
    return {
        "email": "...",
        "password": "...",
        "totp_secret": "...",
        # optional extras you want keeper_login() to see:
        "server": "keepersecurity.com",
        "config_path": "/etc/dsk/keeper.json",
    }


def keeper_login(email: str, password: str, totp_secret: str, **kwargs: Any) -> Any:
    from keepercommander import api
    from keepercommander.params import KeeperParams
    import pyotp

    params = KeeperParams()
    params.user = email
    params.password = password
    params.server = kwargs.get("server", "keepersecurity.com")

    class Ui:
        def on_two_factor(self, *_a, **_kw):
            return pyotp.TOTP(totp_secret).now()
        def on_device_approval(self, *_a, **_kw):
            return True   # or raise if your policy forbids auto-approval

    api.login(params, login_ui=Ui())
    if not getattr(params, "session_token", None):
        from keeper_sdk.core.errors import CapabilityError
        raise CapabilityError(
            reason="login returned no session token",
            next_action="retry; inspect ~/.keeper/ for stale tokens",
        )
    return params
```

```bash
export KEEPER_SDK_LOGIN_HELPER=/opt/dsk/my_login.py
dsk --provider commander apply env.yaml
```

## Error handling contract

Every failure mode **must** raise `keeper_sdk.core.errors.CapabilityError`
with:

- `reason` — one-sentence human description. Include the exception
  type + message if you wrap one.
- `next_action` — a copy-pasteable fix. The CLI prints this on `stderr`
  and exits 5. Agents consume this string verbatim, so keep it
  actionable.

Silent returns from `keeper_login` that produce an unusable
`KeeperParams` are the worst failure mode — the SDK will then proceed
to call `pam project import` which will hang waiting for stdin. Always
assert `params.session_token` before returning.

## Security posture

- `EnvLoginHelper` reads env vars once per provider instance and never
  persists them to disk.
- Custom helpers should do the same. If you must cache, cache in a
  memory-only structure and clear on process exit.
- The `keeper-commander` client itself caches a device token under
  `~/.keeper/`. That is outside the SDK blast radius — treat the
  home directory of any service account running `dsk` as
  privileged.

## Testing your helper

```bash
python -c "
import os
os.environ['KEEPER_SDK_LOGIN_HELPER'] = '/opt/dsk/my_login.py'
from keeper_sdk.auth import load_helper_from_path
h = load_helper_from_path(os.environ['KEEPER_SDK_LOGIN_HELPER'])
print('loaded:', type(h).__name__)
print('creds keys:', list(h.load_keeper_creds().keys()))
"
```

If the last line prints `['email', 'password', 'totp_secret', ...]`, the
import surface is good. Actual login is only exercised at
`dsk apply` time against the `commander` provider.
