# Issue #7: Gateway Create and Projects Design

## Decision

Keep gateway `mode: create` and top-level `projects[]` preview-gated for this
release. This is a design slice, not support. The SDK must not claim gateway
creation or multi-project apply until a non-interactive Commander writer path
is proven with live tenant evidence and a clean re-plan.

Classification: design-only. `reference_existing` remains the supported
gateway mode.

## Target Manifest Shape

Current manifests stay valid and remain the default single-project shape:

```yaml
version: "1"
name: acme-lab
gateways:
  - uid_ref: gw.lab
    name: acme-lab-gateway
    mode: reference_existing
pam_configurations:
  - uid_ref: cfg.local
    title: acme-lab-config
    environment: local
    gateway_uid_ref: gw.lab
resources: []
```

The first supported `projects[]` lift should be compatibility-only: exactly one
project, no batch semantics, and no nested project bodies. `name` continues to
be the manifest/project identity; `projects[0].project` must match it until a
separate schema version makes `name` a batch label.

```yaml
version: "1"
name: acme-lab
projects:
  - uid_ref: proj.acme_lab
    project: acme-lab
gateways:
  - uid_ref: gw.lab
    name: acme-lab-gateway
    mode: create
    ksm_application_name: acme-lab-ksm
pam_configurations:
  - uid_ref: cfg.local
    title: acme-lab-config
    environment: local
    gateway_uid_ref: gw.lab
resources: []
```

Multi-project files are not part of this slice. If they are approved later,
each `projects[]` item must own isolated `shared_folders`, `gateways`,
`pam_configurations`, `resources`, and `users` arrays, with no cross-project
`uid_ref` links except explicit external references. That should be a new
manifest schema shape, not a quiet reinterpretation of today's top-level arrays.

## Gateway Create Boundary

`mode: create` should mean "create or register Keeper control-plane gateway
state if Commander exposes an idempotent, non-interactive writer." It must not
install, start, update, or monitor a gateway process on the operator's machine.

The conservative implementation path is scaffold-first:

1. Resolve the explicit `ksm_application_name`; do not create KSM apps
   implicitly.
2. Produce a deterministic `next_action` or scaffold using the verified
   Commander gateway-create hook.
3. Re-run plan after the operator has a tenant-visible gateway, then converge
   through `mode: reference_existing`.

Direct SDK-driven gateway creation can be considered only after the hook proves
it returns stable JSON identifiers, avoids prompts, redacts bootstrap material,
and can be re-run safely.

## Commander Hooks Required

Already used by the SDK:

- `pam gateway list --format json` to resolve `reference_existing` gateways and
  bound KSM app identity.
- `pam config list --format json` to resolve PAM configuration bindings.
- `pam project import` / `pam project extend` for project data writes.
- `mkdir -uf`, `mkdir -sf`, and `secrets-manager share add` for project folder
  scaffolding and KSM app sharing.

Required before support can be claimed:

- A verified gateway create/register hook. The current provider hint names
  `pam gateway new --application <ksm_app> --config-init json`, but this must be
  checked against the pinned Commander source and exercised in tests before any
  gate is lifted.
- Machine-readable output containing gateway UID, gateway name, bound KSM app
  UID/name, and any generated bootstrap/config material with redaction rules.
- A retry/idempotency contract: existing gateway with the declared name and app
  must become a noop or conflict, never duplicate silently.
- A teardown boundary. Until Commander exposes safe delete/deactivate semantics
  with ownership proof, `allow-delete` must not delete gateways, KSM apps, or
  project folders.

## Ordering and Ownership

The supported ordering should be:

1. Validate schema, preview gate, and semantic rules.
2. Resolve the declared KSM app and existing gateway/config rows.
3. For `mode: create`, run only the approved scaffold/create step, then
   rediscover the tenant state.
4. Ensure project Resources/Users shared folders and KSM app sharing.
5. Import or extend PAM configuration/resources/users.
6. Discover created records and write ownership markers.
7. Re-plan and require zero drift before declaring support.

Ownership rules:

- Vault records keep the existing `keeper_declarative_manager` marker contract.
- Existing unmarked records with matching titles remain conflicts until
  explicitly adopted.
- Gateway, KSM app, project folder, and shared-folder deletion is out of scope
  until those objects have a safe ownership proof. The SDK may ensure them, but
  must not remove them under `--allow-delete`.
- `ksm_application_name` stays explicit. The SDK must not infer or create a KSM
  app from a gateway title.

## Migration

No migration is required for current manifests. The current single-project
shape is canonical for v1.x.

When compatibility `projects[]` support lands:

- A manifest without `projects[]` behaves exactly as it does today.
- A manifest with one `projects[]` entry must set `project` equal to top-level
  `name`; the SDK may synthesize that entry during export/canonicalization.
- A manifest with more than one project stays invalid or preview-conflict until
  a batch design exists.
- `mode: create` users should migrate back to `mode: reference_existing` after
  the gateway is visible on the tenant, unless direct create has live proof.

## Gate Policy

Current gates stay closed:

- `keeper_sdk/core/preview.py` rejects `mode: create` and top-level
  `projects[]` unless `DSK_PREVIEW=1`.
- `CommanderCliProvider.unsupported_capabilities()` reports `mode: create` as a
  plan-time conflict and `apply_plan()` refuses it as a last-line defense.
- `projects[]` remains preview-only; before any provider can claim support, a
  provider conflict must be added for unsupported multi-project semantics when
  `DSK_PREVIEW=1` is used.

Gate lift requires all of:

- Source audit against the pinned Commander checkout.
- Offline mapper/scaffold tests.
- Mocked Commander command contract tests.
- One live disposable-tenant proof for create, converge, clean re-plan, and
  cleanup boundary.
- Docs and examples updated in the same change.

## Next Issue Split

1. `projects[]` compatibility: schema/rules proposal for exactly one project,
   `name == projects[0].project`, normalization/export behavior, and preview
   tests.
2. Gateway create audit: inspect pinned Commander gateway code and document the
   exact non-interactive create/register hook and output shape.
3. Gateway scaffold helper: pure function that builds argv/next-action and
   redacts bootstrap output; no provider wiring.
4. Provider conflict hardening: add explicit Commander conflict for unsupported
   `projects[]` semantics under `DSK_PREVIEW=1`.
5. Live proof slice: disposable gateway/project create path, clean re-plan, and
   documented teardown boundary before removing any preview key.
