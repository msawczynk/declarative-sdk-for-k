# KSM Integration

## Why KSM

KSM lets one audited admin record drive every agent, CI runner, and operator
that needs SDK access. The record stays encrypted at rest, access is controlled
by the KSM application's shared-folder grants, and reads are audit-logged in
the Keeper Web UI.

## Admin login record schema

Create one Keeper record for the Commander admin login with these typed fields:

| Field type | Meaning |
|---|---|
| `login` | Commander admin email |
| `password` | Commander admin password |
| `oneTimeCode` | TOTP `otpauth://` URI |

Web UI screenshot path: `(no image attached)`.

## One-time setup

1. Install:

   ```bash
   pip install 'declarative-sdk-for-k[ksm]'
   ```

2. Create a KSM application in Keeper Web UI; share the admin record into its
   folder.
3. Download the device config to `~/.keeper/caravan-ksm-config.json`, or put it
   anywhere and point `KEEPER_SDK_KSM_CONFIG` at it.
4. Enable the in-tree helper:

   ```bash
   export KEEPER_SDK_LOGIN_HELPER=ksm
   ```

5. Point the helper at the admin record:

   ```bash
   export KEEPER_SDK_KSM_CREDS_RECORD_UID=<uid>
   ```

## Env-var matrix

| Env var | Default | Meaning |
|---|---|---|
| `KEEPER_SDK_KSM_CONFIG` | auto-discover `~/.keeper/caravan-ksm-config.json`, then `~/.keeper/ksm-config.json` | KSM application config path |
| `KEEPER_SDK_KSM_CREDS_RECORD_UID` | none | UID of the record holding Commander login fields |
| `KEEPER_SDK_KSM_LOGIN_FIELD` | `login` | Field type for the Commander email |
| `KEEPER_SDK_KSM_PASSWORD_FIELD` | `password` | Field type for the Commander password |
| `KEEPER_SDK_KSM_TOTP_FIELD` | `oneTimeCode` | Field type for the TOTP URI or base32 secret |
| `KEEPER_SDK_KSM_ALLOW_OTPAUTH_PASSTHROUGH` | unset | Return the raw `otpauth://` URI instead of extracting `secret=` |

## Programmatic SecretStore

```python
from keeper_sdk.secrets import KsmSecretStore

store = KsmSecretStore(config_path="~/.keeper/caravan-ksm-config.json")
db_password = store.field("RECORD_UID", "password")
```

`KsmSecretStore` does not cache decrypted values across instances. Hold one
instance when a short-lived process wants reuse; construct a new one when a
rotation should be observed.

## Auditing

Find KSM access logs in Keeper Web UI under the KSM application's activity and
record access history. The SDK never logs field values. `describe()` returns
shape only: `(type, label, has_value)` tuples plus UID/title prefixes.

## Trade-offs

Compared with `EnvLoginHelper`, `KsmLoginHelper` avoids environment-variable
credential leakage and centralizes access review in Keeper. It adds the optional
`keeper-secrets-manager-core` dependency and a KSM application to manage.
Use `EnvLoginHelper` only for ad-hoc local debugging.

## Future work

Manifest `${ksm:UID:field}` placeholder resolution is on the roadmap. Today,
programmatic use of `KsmSecretStore` is the supported path for non-login
secrets.
