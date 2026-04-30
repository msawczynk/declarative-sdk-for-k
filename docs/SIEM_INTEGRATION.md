# SIEM Integration Manifests

`keeper-siem.v1` models Keeper audit event streaming configuration as
declarative data. It is intended for tenants that forward security events into
SIEM, observability, or archive systems such as Splunk, Datadog, ELK, generic
webhooks, and S3-compatible object storage.

This family is offline-only in the current SDK slice. `dsk validate` checks the
schema and typed model. `dsk plan` and `dsk apply` return a capability error
with `upstream-gap` because no supported Keeper writer/discover hook is modeled
for SIEM integration configuration yet.

## Architecture

A SIEM manifest has two top-level blocks:

| Block | Purpose |
| --- | --- |
| `sinks[]` | Declares delivery targets and per-target buffering/filtering settings. |
| `routes[]` | Maps event type patterns to one or more sink `uid_ref` values. |

Secrets are not stored in the SIEM manifest. The `token` field is a redacted
Keeper vault reference in the form `keeper-vault:records:<uid_ref>`. The record
should contain the Splunk HEC token, Datadog API key, webhook bearer token, or
other delivery credential needed by the downstream integration.

`batch_size` and `flush_interval_sec` describe desired batching behavior. The
model defaults are `500` events and `30` seconds when omitted.

## Supported Sinks

| Type | Endpoint shape | Token use |
| --- | --- | --- |
| `splunk` | Splunk HEC endpoint, for example `https://splunk.example.com:8088/services/collector` | HEC token record reference. |
| `datadog` | Datadog intake URL, for example `https://http-intake.logs.datadoghq.com/api/v2/logs` | API key record reference. |
| `elk` | Elasticsearch or Logstash HTTP endpoint | API key or bearer token record reference when required. |
| `webhook` | HTTPS receiver URL | Optional shared secret or bearer token record reference. |
| `s3` | `s3://bucket/prefix` or S3-compatible endpoint | Optional credential reference when IAM or ambient identity is not used. |

## Event Types

The SDK treats event types as strings so it can validate future Keeper event
names without a schema release. Use exact names for known high-value events and
wildcards in route patterns when a whole family of events should share a sink.

Common event type groups:

| Group | Examples |
| --- | --- |
| Authentication | `login_success`, `login_failure`, `mfa_challenge`, `device_approved` |
| Vault records | `record_create`, `record_update`, `record_delete`, `record_share` |
| Sharing | `shared_folder_create`, `shared_folder_update`, `share_invite_sent` |
| PAM | `pam_session_start`, `pam_session_end`, `pam_rotation_success`, `pam_rotation_failure` |
| Admin | `role_create`, `team_update`, `policy_update`, `user_locked` |
| KSM | `ksm_app_create`, `ksm_secret_access`, `ksm_client_revoked` |

`sinks[].filter.event_types` is an allow list applied at the target. `routes[]`
uses `event_type_patterns` for fan-out. Patterns are declarative strings such
as `login_*`, `record_*`, or `pam_rotation_*`; the current SDK validates the
shape only and does not execute pattern matching.

## Splunk Example

```yaml
schema: keeper-siem.v1
name: prod-siem
manager: keeper-dsk
sinks:
  - uid_ref: sink.splunk.prod
    name: Splunk prod HEC
    type: splunk
    endpoint: https://splunk.example.com:8088/services/collector
    token: keeper-vault:records:rec.splunk-hec-token
    filter:
      event_types:
        - login_failure
        - record_delete
        - pam_rotation_failure
      severity_min: medium
    batch_size: 1000
    flush_interval_sec: 15
routes:
  - uid_ref: route.security-critical
    event_type_patterns:
      - login_*
      - record_*
      - pam_rotation_*
    sink_uid_refs:
      - sink.splunk.prod
```

## Datadog Example

```yaml
schema: keeper-siem.v1
name: prod-datadog-events
sinks:
  - uid_ref: sink.datadog.security
    name: Datadog security intake
    type: datadog
    endpoint: https://http-intake.logs.datadoghq.com/api/v2/logs
    token: keeper-vault:records:rec.datadog-api-key
    filter:
      event_types:
        - login_success
        - login_failure
        - record_share
      severity_min: low
routes:
  - uid_ref: route.auth-and-sharing
    event_type_patterns:
      - login_*
      - record_share
      - shared_folder_*
    sink_uid_refs:
      - sink.datadog.security
```

## Current CLI Behavior

```bash
dsk validate siem.yaml --json
dsk plan siem.yaml --json        # exits 5, upstream-gap
dsk apply siem.yaml --dry-run    # exits 5, upstream-gap
```

Use `keeper_sdk.core.siem_diff.compute_siem_diff()` for offline unit tests or
tooling that compares a desired manifest with a supplied snapshot.
