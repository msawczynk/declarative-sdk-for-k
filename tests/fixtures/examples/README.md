# Examples

Canonical and failure fixtures for Keeper declarative manifest families.

All YAML files here must be valid against their declared `schema` family, or
legacy PAM `version: "1"` shape, **except** those under `invalid/`, which must
fail validation and serve as negative-space coverage.

## Valid

- `minimal/environment.yaml` — smallest valid manifest (one shared folder, one referenced gateway, one local PAM configuration, one pamMachine with one nested pamUser).
- `full-local/environment.yaml` — every v1 resource type (pamMachine SSH + RDP, pamDatabase MySQL, pamDirectory AD, pamRemoteBrowser) under environment `local`, with rotation, tunneling, RBI autofill, session recording, AI risk rules, JIT.
- `aws-iam-rotation/environment.yaml` — `environment: aws`, iam_user rotation on a managed IAM user, reference-existing gateway.
- `domain-rotation/environment.yaml` — `environment: domain`, scan + admin-credential uid_ref.
- `workflow/environment.yaml` — `keeper-workflow.v1` schema/model scaffold.
- `privileged-access/environment.yaml` — `keeper-privileged-access.v1` schema/model scaffold.
- `tunnel/environment.yaml` — `keeper-tunnel.v1` schema/model scaffold.
- `saas-rotation/environment.yaml` — `keeper-saas-rotation.v1` schema/model scaffold.
- `keeper-drive/environment.yaml` — private-only `keeper-drive.v1` schema/model scaffold.

## Invalid (must fail validation)

- `invalid/duplicate-uid-ref.yaml` — two resources share the same `uid_ref`.
- `invalid/missing-ref.yaml` — `*_uid_ref` points at a uid_ref that does not exist in the manifest.
- `invalid/admin-cred-not-found.yaml` — `administrative_credentials` by-title string resolves to no user.
- `invalid/gateway-create-in-unsupported-env.yaml` — `gateways[].mode: create` without required `ksm_application_name`.
- `invalid/cyclic-refs.yaml` — two users admin-cred each other (cycle).
- `invalid/rbi-rotation-on.yaml` — pamRemoteBrowser enables `rotation` in options (not allowed).
- `invalid/env-field-mismatch.yaml` — `aws_access_key_id` under `environment: local`.

## Placeholders

Fixtures use obvious placeholders only. Never commit real credentials.
