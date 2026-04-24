# Validation stages and exit codes

`dsk validate` runs a layered check. The layers are cumulative — stage N
only executes if stages 1 through N-1 all passed. `--online` enables
stages 4 and 5; without it, validation stops after stage 3.

Every stage has a deterministic exit code so CI pipelines can branch on
the specific failure class without parsing stderr.

## The five stages

| Stage | Name | Failure exit code | What it checks | Requires `--online` |
|------:|------|:-----------------:|----------------|:-------------------:|
| 1 | JSON Schema (structural) | `EXIT_SCHEMA` (`2`) | Manifest parses, required keys present, type-narrow unions resolve, `pam-environment.v1.schema.json` passes `jsonschema.validate`. | no |
| 2 | Typed model | `EXIT_SCHEMA` (`2`) | Pydantic v2 validation, enum coercion, canonical field-name rule (aliases fold to canonical). | no |
| 3 | Manifest-internal references | `EXIT_REF` (`3`) | Every `*_uid_ref` targets a declared `uid_ref`; no cycles; ownership-marker shape is sane. | no |
| 4 | Tenant-side capabilities | `EXIT_CAPABILITY` (`5`) | Session active, `discover()` works, gateways declared as `reference_existing` exist on the tenant, provider `unsupported_capabilities()` returns `[]`. | **yes** |
| 5 | Tenant-side bindings | `EXIT_CAPABILITY` (`5`) | Provider `check_tenant_bindings()` returns `[]`. For commander: pam_configuration titles resolve, shared_folder bindings exist on each config, `gateway_uid_ref` pairings match the live gateway UID, declared `ksm_application_name` matches the tenant's. | **yes** |

Success path (all stages pass) exits `0`.

## Exit code semantics

- `0` (`EXIT_OK`) — validation passed all enabled stages.
- `1` (`EXIT_GENERIC`) — unexpected error. Look at stderr.
- `2` (`EXIT_SCHEMA` for `validate`; `EXIT_CHANGES` for `plan` / `diff`)
  — **intentionally overloaded**. From `validate` it means "schema or
  typed-model invalid" (failure). From `plan` / `diff` it means
  "changes are present" (informational, not a failure). Operators and
  CI pipelines disambiguate by the subcommand they invoked. CI depends
  on this; see also `AGENTS.md` exit-code table.
- `3` (`EXIT_REF`) — manifest-internal reference error: cycle, dangling
  `*_uid_ref`, duplicate `uid_ref`. Fix the manifest.
- `4` (`EXIT_CONFLICT`) — plan has `ChangeKind.CONFLICT` rows. Read
  `plan --json` and iterate `changes[*].reason`. Emitted by `plan` /
  `apply --dry-run` / `apply`, not by `validate`.
- `5` (`EXIT_CAPABILITY`) — the manifest is structurally fine but the
  tenant can't execute it: missing gateway (stage 4), unsupported
  capability the provider hasn't implemented yet (stage 4), missing
  PAM configuration (stage 5), gateway pairing mismatch (stage 5),
  shared-folder binding missing (stage 5). Fix the tenant or shrink
  the manifest.

The numeric values are part of the **binding CLI contract**: CI
pipelines depend on them. Do not reorder without a major version bump.

## Examples

### Passing run (online)

```bash
$ DSK_PREVIEW=1 dsk validate manifests/prod.yaml --online
stage 5: 0 create, 3 update, 0 delete-candidates, 0 conflicts
ok: prod (17 uid_refs); online: 24 live records
$ echo $?
0
```

### Stage-4 failure (gateway missing)

```bash
$ dsk validate manifests/prod.yaml --online
stage 4: gateway 'acme-prod-gw' not found in tenant
$ echo $?
5
```

### Stage-5 failure (config missing)

```bash
$ dsk validate manifests/prod.yaml --online
stage 5: 1 create, 2 update, 0 delete-candidates, 0 conflicts
stage 5: tenant binding failures:
  - pam_configuration 'Prod AWS Config' (uid_ref=cfg-aws-prod) not found on tenant; declare a matching title or create the configuration in Keeper first
  - pam_configuration 'Prod AWS Config' declares gateway_uid_ref='gw-primary' (uid=G1234567...) but tenant pairs it with gateway uid 'G8901234...'
$ echo $?
5
```

### Stage-3 failure (dangling ref)

```bash
$ dsk validate manifests/prod.yaml
reference error: resources[1].pam_configuration_uid_ref='cfg-missing' does not match any declared uid_ref
$ echo $?
3
```

## Remediation pointers

| Failure | Likely fix |
|---|---|
| stage 4: gateway not found | Start the gateway container, or change `mode: reference_existing → create` (preview). |
| stage 5: pam_configuration not found | Create the configuration in the Keeper vault (UI or `pam config new`), then retry. The SDK does not create configurations — it binds to existing ones. |
| stage 5: pam_configuration has no shared_folder | The configuration was created without a shared folder — recreate it, or select a different configuration. |
| stage 5: gateway pairing mismatch | Either edit the manifest's `gateway_uid_ref` to match the live pairing, or re-pair the configuration to the expected gateway in Keeper. |
| stage 5: ksm_application_name mismatch | Same as pairing mismatch — declared KSM app must match the one actually bound in the tenant. |

## Why stages 4 and 5 are split

Stage 4 is the gate: if enforcements block the session or the gateway
doesn't exist, stage 5's detail-level binding checks can't run
meaningfully. Stage 5 assumes the tenant is reachable and the gateway
exists — it just verifies every declared binding inside that reachable
surface lines up.

Both map to the same exit code (`5`) because both are "tenant side
can't execute this manifest today." Operators get the specific cause
from stderr; CI pipelines get a uniform blocking signal.
