# Crossplane Integration

DSK's Crossplane integration is an offline, preview-gated foundation. It
defines Kubernetes-facing API stubs and a Python provider boundary, but it does
not yet ship a Crossplane package, controller image, gRPC function server, or
live Keeper reconciliation path.

## Status

| Surface | Status | Notes |
|---------|--------|-------|
| `KeeperRecord.v1alpha1` XRD | preview-gated stub | Maps to `keeper-vault.v1` `records[]` with `type: login`. |
| `KeeperSharedFolder.v1alpha1` XRD | preview-gated stub | Maps to `keeper-vault-sharing.v1` `shared_folders[]`. |
| Compositions | preview-gated stub | Pipeline-mode references a future `function-dsk-cli`. |
| Python provider | preview-gated stub | `CrossplaneProvider` imports offline and raises `CapabilityError` for every lifecycle method. |
| Live cluster support | not implemented | No Kubernetes API calls, no Commander calls, and no live smoke proof. |

## Architecture

```text
Kubernetes user
  -> KeeperRecord / KeeperSharedFolder composite resource
  -> Crossplane Composition (Pipeline mode)
  -> function-dsk-cli (future Crossplane Function)
  -> DSK manifest fragment
  -> dsk validate -> dsk plan -> dsk apply
  -> Keeper tenant
```

The checked-in stubs are intentionally shaped around DSK's existing manifest
families:

- `crossplane/xrds/keeperrecord.xrd.yaml` exposes `spec.parameters` for a
  Keeper login record and maps to:

  ```yaml
  schema: keeper-vault.v1
  records:
    - uid_ref: ...
      type: login
      title: ...
      fields: [...]
  ```

- `crossplane/xrds/keepersharedfolder.xrd.yaml` exposes shared-folder path and
  default permissions and maps to:

  ```yaml
  schema: keeper-vault-sharing.v1
  shared_folders:
    - uid_ref: ...
      path: ...
      defaults: ...
  ```

- `crossplane/compositions/*.composition.yaml` uses Crossplane Pipeline mode and
  references `function-dsk-cli`. The input kind, `DskCliReconcile`, is a DSK
  placeholder contract. It is not a published Crossplane function API.

## Using DSK as a Crossplane Function

The intended lift path is a Crossplane Function that wraps the DSK CLI or the
same Python core used by the CLI:

1. Install the XRDs and Compositions into a Crossplane control plane.
2. Install a `Function` package named `function-dsk-cli`.
3. The function receives a `RunFunctionRequest` from Crossplane, reads the
   composite resource parameters, renders a minimal DSK manifest, and runs
   offline validation.
4. Observe maps to `dsk plan --json`. A clean plan reports ready state; changes
   report pending create/update/delete.
5. Create and update map to `dsk apply --auto-approve`.
6. Delete maps to an explicit DSK delete flow with `--allow-delete`, scoped only
   to records owned by the DSK marker.

Crossplane Composition Functions run as gRPC servers and are invoked from
Pipeline-mode Compositions. See the Crossplane Composition documentation:
https://docs.crossplane.io/latest/composition/compositions/

## Provider Controller Stub

`keeper_sdk.crossplane.CrossplaneProvider` is the Python boundary for a future
controller or function implementation. It currently implements these method
names only:

- `plan()`
- `apply()`
- `observe()`
- `create()`
- `update()`
- `delete()`
- Provider protocol hooks: `discover()`, `apply_plan()`,
  `unsupported_capabilities()`, and `check_tenant_bindings()`

Every method raises `CapabilityError` with `next_action` pointing back to this
document. This preserves a fail-closed preview gate: users can import the
module and inspect the API surface, but no tenant mutation can happen.

## Comparison With Upjet

Upjet generates Crossplane providers from Terraform provider schemas and
runtime conventions. That is a good comparison point for a mature provider
package, but DSK is not currently Terraform-backed and already has a
manifest-first lifecycle. A DSK Crossplane provider would likely start as a
function/controller wrapper around DSK manifests, not an Upjet-generated
Terraform bridge.

Reference: https://github.com/crossplane/upjet

## Requirements To Lift The Gate

Crossplane support should stay preview-gated until all of these exist:

- A packaged Crossplane Function or provider controller image.
- A stable function input schema replacing the placeholder `DskCliReconcile`.
- A credential model for Keeper Commander/KSM secrets that does not echo
  secrets into function logs, Kubernetes events, or DSK output.
- Deterministic manifest rendering from `spec.parameters`, including
  Kubernetes Secret resolution for Keeper record passwords.
- Status mapping from DSK plans/outcomes to Crossplane conditions.
- Delete semantics that preserve DSK ownership-marker rules and require
  explicit delete intent.
- Offline tests for rendering, error mapping, and capability gates.
- Live smoke proof in a lab cluster and Keeper tenant using the committed smoke
  harness pattern, with sanitized transcripts under `docs/live-proof/`.
