# Validation stages and exit codes

`dsk validate` runs a layered check. **Family dispatch:**

- **`schema: pam-environment.v1`** (and legacy PAM manifests with `version` +
  `name`) run the full PAM stack below.
- **`schema: keeper-vault.v1`** runs JSON Schema, typed
  ``VaultManifestV1`` load, and
  ``build_vault_graph`` (stages 1–3 analogue to PAM). With ``--online`` and
  ``--provider commander`` plus folder scope, it runs **tenant** stages 4–5
  (``discover``, ``unsupported_capabilities``, ``check_tenant_bindings``,
  ``compute_vault_diff``) — same exit codes as PAM; there is **no** PAM gateway
  ``reference_existing`` probe on vault paths. Offline ``plan`` / ``diff`` use the
  same ``compute_vault_diff`` rules: manifest ``login`` ``fields[]`` is compared
  to flattened Commander-style live payloads so benign shape drift does not look
  like drift when values agree (see ``tests/test_vault_diff.py``).
- **Other packaged non-PAM families** complete stages 1–2 (JSON Schema + rules
  that apply) then exit success without typed PAM ``Manifest`` load, uid_ref
  graph, or tenant probes (see ``docs/PAM_PARITY_PROGRAM.md``).

Use ``dsk validate --json`` for a machine-readable summary (``mode``:
``schema_only``, ``pam_full``, ``vault_offline``, or ``vault_online``).

The layers are cumulative per family — stage N only executes if stages 1
through N-1 all passed for that family. ``--online`` enables stages 4 and 5 for
**PAM** and **keeper-vault.v1**; without it, those families stop after offline
stage 3.

Every stage has a deterministic exit code so CI pipelines can branch on
the specific failure class without parsing stderr.

## The five stages

| Stage | Name | Failure exit code | What it checks | Requires `--online` |
|------:|------|:-----------------:|----------------|:-------------------:|
| 1 | JSON Schema (structural) | `EXIT_SCHEMA` (`2`) | Manifest parses; family resolved from `schema:` or legacy PAM keys; packaged JSON Schema for that family passes `jsonschema.validate`. `dropped-design` families fail here. | no |
| 2 | Typed model | `EXIT_SCHEMA` (`2`) | **PAM:** Pydantic v2 validation, enum coercion, canonical field-name rule (aliases fold to canonical). **Vault:** ``VaultManifestV1`` + L1 ``login``-only rule. Other non-PAM families skip this stage. | no |
| 3 | Manifest-internal references | `EXIT_REF` (`3`) | **PAM:** every `*_uid_ref` targets a declared `uid_ref`; no cycles; ownership-marker shape is sane. **Vault:** ``build_vault_graph`` (``uid_ref`` / ``folder_ref``). | no |
| 4 | Tenant-side capabilities | `EXIT_CAPABILITY` (`5`) | Session active, ``discover()`` works, provider ``unsupported_capabilities()`` returns ``[]``. **PAM adds:** gateways declared as ``reference_existing`` exist on the tenant. | **yes** |
| 5 | Tenant diff smoke + bindings | `EXIT_CAPABILITY` (`5`) | After stage 4, **PAM** runs ``compute_diff`` and **vault** runs ``compute_vault_diff`` (``OwnershipError`` → exit **5**). Stdout labels the create/update/delete/conflict counts **stage 5**. Then ``check_tenant_bindings()`` must return ``[]`` (**PAM** Commander: pam_configuration titles, shared folders, ``gateway_uid_ref``, ``ksm_application_name``; **vault** Commander: hook is a no-op today). | **yes** |

Success path (all stages pass) exits `0`.

Stage 3 is also the current guard for `pam_configuration_uid_ref`
scope. In-manifest linking is GA: every resource may point at a
`pam_configuration.uid_ref` declared in the same manifest, and that
continues to work. Cross-manifest / live-tenant-config linking is
deferred to v1.1, so a resource whose `pam_configuration_uid_ref`
targets a config that is not declared in the manifest currently fails
as an unresolved reference and exits `3`.

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

### Passing run (vault, online)

```bash
$ dsk --provider commander --folder-uid "$KEEPER_DECLARATIVE_FOLDER" \
    validate examples/scaffold_only/vaultMinimal.yaml --online --json
{"ok": true, "family": "keeper-vault.v1", "mode": "vault_online", ...}
$ echo $?
0
```

Requires an authenticated Commander session and a folder UID scoped to the
vault under test.

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
surface lines up. If Commander CLI output cannot prove a gateway's
`ksm_application_name` binding, stage 5 fails closed and points the
operator at a manual Keeper UI check rather than silently passing.

**Vault:** there is no PAM gateway pre-check; stage 4 is ``discover`` +
capability gaps, stage 5 is diff smoke plus vault-specific binding checks
(today a no-op for L1).

Both map to the same exit code (`5`) because both are "tenant side
can't execute this manifest today." Operators get the specific cause
from stderr; CI pipelines get a uniform blocking signal.
