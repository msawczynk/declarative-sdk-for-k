# Examples

Canonical and failure fixtures for the Keeper PAM declarative manifest v1.

All YAML files here must be valid against `../manifests/pam-environment.v1.schema.json` **except** those under `invalid/`, which must fail validation and serve as negative-space coverage.

## Valid

- `minimal/environment.yaml` — smallest valid manifest (one shared folder, one referenced gateway, one local PAM configuration, one pamMachine with one nested pamUser).
- `full-local/environment.yaml` — every v1 resource type (pamMachine SSH + RDP, pamDatabase MySQL, pamDirectory AD, pamRemoteBrowser) under environment `local`, with rotation, tunneling, RBI autofill, session recording, AI risk rules, JIT.
- `aws-iam-rotation/environment.yaml` — `environment: aws`, iam_user rotation on a managed IAM user, reference-existing gateway.
- `domain-rotation/environment.yaml` — `environment: domain`, scan + admin-credential uid_ref.

## Invalid (must fail validation)

- `invalid/duplicate-uid-ref.yaml` — two resources share the same `uid_ref`.
- `invalid/missing-ref.yaml` — `*_uid_ref` points at a uid_ref that does not exist in the manifest.
- `invalid/admin-cred-not-found.yaml` — `administrative_credentials` by-title string resolves to no user.
- `invalid/gateway-create-in-unsupported-env.yaml` — `gateways[].mode: create` without `ksm_application_name` or capability.
- `invalid/cyclic-refs.yaml` — two users admin-cred each other (cycle).
- `invalid/rbi-rotation-on.yaml` — pamRemoteBrowser enables `rotation` in options (not allowed).
- `invalid/env-field-mismatch.yaml` — `aws_access_key_id` under `environment: local`.

## Placeholders

Fixtures use obvious placeholders only. Never commit real credentials.
