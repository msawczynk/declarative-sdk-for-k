# KSM Integration

## Why KSM

KSM lets one audited admin record drive every agent, CI runner, and operator
that needs SDK access. The record stays encrypted at rest, access is controlled
by the KSM application's shared-folder grants, and reads are audit-logged in
the Keeper Web UI.

## Bootstrap

Use [`dsk bootstrap-ksm`](./KSM_BOOTSTRAP.md) as the recommended production
on-ramp. It provisions the KSM application, shares the admin login record,
redeems a client config, and verifies the config before you switch steady-state
SDK runs to `KsmLoginHelper`.

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

2. Authenticate the source admin Commander session once:

   ```bash
   keeper login
   ```

3. Bootstrap KSM:

   ```bash
   dsk bootstrap-ksm \
     --app-name dsk-service-admin \
     --admin-record-uid <uid> \
     --config-out ~/.keeper/dsk-service-admin-ksm-config.json
   ```

4. Enable the in-tree helper:

   ```bash
   export KEEPER_SDK_LOGIN_HELPER=ksm
   ```

5. Point the helper at the admin record and config:

   ```bash
   export KEEPER_SDK_KSM_CREDS_RECORD_UID=<uid>
   export KEEPER_SDK_KSM_CONFIG=~/.keeper/dsk-service-admin-ksm-config.json
   ```

Manual fallback: if you cannot use interactive Commander, create the KSM
application in Keeper Web UI, share the admin record into the app, download the
device config to disk, and set `KEEPER_SDK_KSM_CONFIG` to that path.

## Declarative app lifecycle

`keeper-ksm.v1` is currently a schema-only marker for KSM integration evidence.
It does not yet model `ksm_apps`, `ksm_clients`, or share bindings, and `dsk
plan` / `dsk apply` intentionally reject the family as a capability gap. Use
`dsk bootstrap-ksm` for the supported create/bind/share/config-redemption path.

A future declarative KSM lifecycle must add a typed manifest body, graph and
diff support, provider create/share/client/delete primitives, clean re-plan
readback, and cleanup proof before the SDK claims app lifecycle support.

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

## Inter-agent Bus

`KsmBus` is a basic key/value coordination bus backed by custom text fields on
one shared KSM record. Bootstrap can create the record with
`--create-bus-directory`; share that record into every agent's KSM application.

```python
from keeper_sdk.secrets import KsmSecretStore
from keeper_sdk.secrets.bus import KsmBus

store = KsmSecretStore(config_path="~/.keeper/dsk-service-admin-ksm-config.json")
bus = KsmBus(store, "<bus-record-uid>")

bus.put("phase7.worker-a.status", "ready")
status = bus.get("phase7.worker-a.status")
```

`get()` returns `None` when a key has no field yet. If the bus record UID is
not configured, `KsmBus` keeps the sealed `NotImplementedError` fallback with a
`next_action` string instead of writing to an unknown record.

The richer publish/subscribe `BusClient` remains a sealed design stub until
cursor/CAS semantics, retention, and operator debug workflow are designed and
live-proven. Design doc placeholder: `docs/KSM_BUS.md`.

## Future work

Manifest `${ksm:UID:field}` placeholder resolution and declarative KSM app
lifecycle resources are on the roadmap. Today, programmatic use of
`KsmSecretStore` is the supported path for non-login secrets, and
`dsk bootstrap-ksm` is the supported KSM app provisioning path.
