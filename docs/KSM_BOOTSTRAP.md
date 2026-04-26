# KSM Bootstrap

## What this does

`dsk bootstrap-ksm` provisions the first Keeper Secrets Manager application for
the SDK: it creates or reuses the KSM app, shares the Commander admin login
record into that app, generates and redeems a client token, writes
`ksm-config.json`, and verifies the resulting client can see the admin record.
After that, use `KsmLoginHelper` as described in
[`KSM_INTEGRATION.md`](./KSM_INTEGRATION.md).

## Prerequisites

- `keeper login` has authenticated the source admin Commander session.
- The SDK was installed with KSM support:

  ```bash
  pip install 'declarative-sdk-for-k[ksm]'
  ```

- The authenticated Keeper account can create vault records, create KSM
  applications, share records into KSM applications, and generate KSM clients.

## Quickstart

Use an existing admin login record:

```bash
dsk bootstrap-ksm \
  --app-name dsk-service-admin \
  --admin-record-uid <ADMIN_RECORD_UID> \
  --config-out ~/.keeper/dsk-service-admin-ksm-config.json \
  --first-access-minutes 10
```

Then enable the steady-state helper:

```bash
export KEEPER_SDK_LOGIN_HELPER=ksm
export KEEPER_SDK_KSM_CREDS_RECORD_UID=<ADMIN_RECORD_UID>
export KEEPER_SDK_KSM_CONFIG=~/.keeper/dsk-service-admin-ksm-config.json
```

Flag notes:

- `--app-name` is the KSM application title. It must be 64 characters or fewer.
- `--admin-record-uid` shares an existing login record into the app.
- `--create-admin-record` creates a placeholder login/password/oneTimeCode
  record instead; populate it in Keeper Web UI before using `KsmLoginHelper`.
- `--config-out` chooses where the redeemed client config is written.
- `--first-access-minutes` controls token first-access expiry. The token is
  redeemed during bootstrap, so the timestamp is audit metadata after success.
- `--unlock-ip` disables KSM IP locking for the new client.

## Idempotent Re-bootstrap

Reusing the same `--app-name` is supported. The command reuses an existing app
with that title, shares the requested admin record, generates a fresh client,
and writes a fresh config.

Use `--overwrite` when replacing an existing config at the same `--config-out`
path. Without it, the command refuses to overwrite the file.

For token rotation planning, use a long-lived app plus short client lifetimes:
set `--first-access-minutes 0` only when you intend to manage first access
manually, then create future clients with Commander:

```bash
keeper secrets-manager client add <APP_UID>
```

## Bus

`--with-bus` creates or reuses a vault record titled
`dsk-agent-bus-directory` with a custom JSON field labelled `topics`. The record
is shared into the KSM app with write access because the future bus will carry
write traffic.

The read/write/CAS library API for the bus is not shipped yet. Treat this as a
Phase B preview hook.

## Cleanup

To undo a bootstrap, remove the KSM app and any records created only for the
bootstrap:

```bash
keeper secrets-manager app remove <APP_UID>
keeper rm <RECORD_UID>
```

Do not remove the existing admin login record unless you created it only for a
discarded bootstrap.

## Audit Trail

Keeper Web UI Event Reporting shows the KSM application, share, client, and
Secrets Manager access events under `secrets-manager` activity.

## What This Does Not Do

- It does not enrol TOTP for the admin record. The operator must populate or
  enrol the record in Keeper Web UI.
- It does not revoke prior KSM clients or tokens. Use Commander client revoke
  workflows for that.
- It does not rotate the admin password. Use the SDK rotation surface once that
  workflow is GA.
