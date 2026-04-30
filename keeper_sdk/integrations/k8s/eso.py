"""Kubernetes External Secrets Operator YAML generators."""

from __future__ import annotations

from typing import Any

from keeper_sdk.core.models_k8s_eso import EsoStore, ExternalSecret

ESO_API_VERSION = "external-secrets.io/v1"
KSM_CONFIG_KEY = "ksm_config"


def generate_cluster_secret_store(store: EsoStore) -> dict[str, Any]:
    """Generate an ESO ``ClusterSecretStore`` using the Keeper KSM provider."""
    return {
        "apiVersion": ESO_API_VERSION,
        "kind": "ClusterSecretStore",
        "metadata": {
            "name": store.name,
        },
        "spec": {
            "provider": {
                "keepersecurity": {
                    "authRef": {
                        "name": store.ks_uid,
                        "key": KSM_CONFIG_KEY,
                        "namespace": store.namespace,
                    },
                },
            },
        },
    }


def generate_external_secret(es: ExternalSecret) -> dict[str, Any]:
    """Generate an ESO ``ExternalSecret`` backed by a Keeper ``ClusterSecretStore``."""
    return {
        "apiVersion": ESO_API_VERSION,
        "kind": "ExternalSecret",
        "metadata": {
            "name": es.name,
        },
        "spec": {
            "secretStoreRef": {
                "name": es.store_ref,
                "kind": "ClusterSecretStore",
            },
            "target": {
                "name": es.target_k8s_secret,
                "creationPolicy": "Owner",
            },
            "data": [_external_secret_data(row) for row in es.data],
        },
    }


def _external_secret_data(row: Any) -> dict[str, Any]:
    remote_ref = {"key": row.keeper_uid_ref}
    if row.property is not None:
        remote_ref["property"] = row.property
    return {
        "secretKey": row.remote_key,
        "remoteRef": remote_ref,
    }
