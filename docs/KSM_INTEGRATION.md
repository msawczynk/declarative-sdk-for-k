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

`KsmBus` is a low-volume coordination bus backed by custom text fields on one
shared KSM record. Bootstrap can create the record with
`--create-bus-directory`; share that record into every agent's KSM application.
Each bus key maps to one custom text field whose `value[0]` is a JSON envelope:

```json
{"schema":"keeper-sdk.ksm-bus.v1","value":{"state":"ready"},"version":1,"updated_at":"2026-04-29T12:00:00Z"}
```

### Key/value API

```python
from keeper_sdk.secrets import KsmSecretStore
from keeper_sdk.secrets.bus import KsmBus, VersionConflict

store = KsmSecretStore(config_path="~/.keeper/dsk-service-admin-ksm-config.json")
bus = KsmBus(store, "<bus-record-uid>")

version = bus.publish("phase13.worker-a.status", {"state": "ready"}, expected_version=0)
value, version = bus.get("phase13.worker-a.status")

try:
    bus.publish("phase13.worker-a.status", {"state": "done"}, expected_version=version)
except VersionConflict as exc:
    print(exc.actual_version)

bus.delete("phase13.worker-a.status")
```

Methods:

| Method | Meaning |
|---|---|
| `publish(key, value, expected_version=None) -> int` | JSON-encodes `value`, increments the field version, writes the custom text field, and returns the new version. If `expected_version` is set and does not match the stored version, raises `VersionConflict`. Use `expected_version=0` for create-only writes. |
| `get(key) -> (value, version) | None` | Reads and decodes the field. Missing keys return `None`. Legacy raw `put()` fields read as version `0`. |
| `delete(key) -> None` | Removes all custom fields with that label. Missing keys are a no-op. |
| `subscribe(key, poll_interval=5)` | Generator yielding `(value, version)` whenever the decoded value or version changes. |
| `put(key, value)` | Backward-compatible raw string write. Prefer `publish()` for new code because it carries version metadata. |

CAS is a client-side protocol over the version stored in the KSM custom field.
It prevents stale writers that pass an old `expected_version` from overwriting a
newer value. Keeper's KSM Python SDK does not document a native conditional
write primitive, so multi-writer race behavior remains `preview-gated` until a
sanctioned live proof characterizes `SecretsManager.save(record)` under
concurrent updates.

Writes use `SecretsManager.save(record)` when the KSM SDK exposes it. Offline
unit tests mock that method; live verification must use the committed smoke /
live-test runbook rather than ad hoc Keeper calls. If a client lacks
`save(record)`, mutating methods raise `CapabilityError` with a `next_action`.

### Message client

`BusClient` stores ordered channel message lists on top of `KsmBus`. It is for
small agent handoffs, not a general queue.

```python
from keeper_sdk.secrets.bus import BusClient

sender = BusClient(store=store, directory_uid="<bus-record-uid>", agent_id="worker-a")
receiver = BusClient(store=store, directory_uid="<bus-record-uid>", agent_id="worker-b")

message_id = sender.send(
    to="worker-b",
    subject="plan-ready",
    payload={"path": "/tmp/plan.json"},
    channel="phase13",
)

messages = receiver.receive(channel="phase13")
receiver.ack(last_id=message_id, consumer="worker-b")
```

Methods:

| Method | Meaning |
|---|---|
| `send(...)` / `publish(...) -> str` | Appends one `BusMessage` to `dsk.bus.channel.<channel>` using CAS retry; returns the sortable message id. |
| `receive(...)` / `subscribe(...) -> list[BusMessage]` | Reads a channel, filters by `consumer` / recipient (`*` receives broadcast), filters expired messages, and returns id-sorted messages after `since_id`. |
| `ack(last_id, consumer)` | Writes a cursor field at `dsk.bus.cursor.<channel>.<consumer>`. The SDK records the cursor but does not hide already-read messages automatically. |
| `gc(now=None) -> int` | Removes expired messages from the client's default channel and returns the number removed. |

## Future work

Manifest `${ksm:UID:field}` placeholder resolution and declarative KSM app
lifecycle resources are on the roadmap. Today, programmatic use of
`KsmSecretStore` is the supported path for non-login secrets, and
`dsk bootstrap-ksm` is the supported KSM app provisioning path.
