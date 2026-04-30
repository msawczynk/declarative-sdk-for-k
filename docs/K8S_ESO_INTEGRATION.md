# Kubernetes ESO Integration

`keeper-k8s-eso.v1` is an offline scaffold for syncing Keeper records into
Kubernetes through the External Secrets Operator (ESO). DSK owns validation,
typed manifests, KSM lifecycle coordination, and deterministic Kubernetes YAML
rendering. ESO owns reconciliation into native Kubernetes `Secret` objects.

```text
Keeper Vault record
        |
        v
Keeper Secrets Manager app/config
        |
        v
External Secrets Operator keepersecurity provider
        |
        v
Kubernetes Secret
```

The integration uses the Keeper Security provider maintained for ESO:
https://github.com/keeper-security/external-secrets-provider

## How DSK And ESO Work Together

Use `keeper-ksm.v1` to model the Keeper Secrets Manager application and record
shares. Use `keeper-k8s-eso.v1` to model the Kubernetes resources ESO needs to
read those records. In this scaffold, `dsk validate` checks the manifest and the
Python helpers render Kubernetes dictionaries that can be serialized as YAML.

`dsk plan` and `dsk apply` intentionally return a capability error for
`keeper-k8s-eso.v1`. DSK does not call Kubernetes, install ESO, or create
cluster resources. The Kubernetes applier remains `kubectl`, GitOps, Helm, or a
cluster controller.

`EsoStore.ks_uid` maps to the Kubernetes `Secret` name that contains the base64
KSM config. The generated `ClusterSecretStore` reads key `ksm_config` from that
secret in `EsoStore.namespace`.

## Example Manifest

```yaml
schema: keeper-k8s-eso.v1
eso_stores:
  - name: keeper-prod
    ks_uid: ksm-config-secret
    namespace: external-secrets
external_secrets:
  - name: database-credentials
    store_ref: keeper-prod
    target_k8s_secret: database-credentials
    data:
      - keeper_uid_ref: ABC123
        remote_key: username
        property: login
      - keeper_uid_ref: ABC123
        remote_key: password
        property: password
```

## Example ClusterSecretStore

```yaml
apiVersion: external-secrets.io/v1
kind: ClusterSecretStore
metadata:
  name: keeper-prod
spec:
  provider:
    keepersecurity:
      authRef:
        name: ksm-config-secret
        key: ksm_config
        namespace: external-secrets
```

## Example ExternalSecret

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: database-credentials
spec:
  secretStoreRef:
    name: keeper-prod
    kind: ClusterSecretStore
  target:
    name: database-credentials
    creationPolicy: Owner
  data:
    - secretKey: username
      remoteRef:
        key: ABC123
        property: login
    - secretKey: password
      remoteRef:
        key: ABC123
        property: password
```
