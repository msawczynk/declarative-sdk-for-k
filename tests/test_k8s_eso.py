"""keeper-k8s-eso.v1 schema, typed model, YAML, and CLI boundary tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY
from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.manifest import load_declarative_manifest_string
from keeper_sdk.core.models_k8s_eso import (
    K8S_ESO_FAMILY,
    K8sEsoManifestV1,
    load_k8s_eso_manifest,
)
from keeper_sdk.core.schema import load_schema_for_family, validate_manifest
from keeper_sdk.integrations.k8s import (
    generate_cluster_secret_store,
    generate_external_secret,
)


def _doc() -> dict[str, Any]:
    return {
        "schema": K8S_ESO_FAMILY,
        "eso_stores": [
            {
                "name": "keeper-prod",
                "ks_uid": "ksm-config-secret",
                "namespace": "external-secrets",
            }
        ],
        "external_secrets": [
            {
                "name": "database-credentials",
                "store_ref": "keeper-prod",
                "target_k8s_secret": "database-credentials",
                "data": [
                    {
                        "keeper_uid_ref": "ABC123",
                        "remote_key": "username",
                        "property": "login",
                    },
                    {
                        "keeper_uid_ref": "ABC123",
                        "remote_key": "password",
                        "property": "password",
                    },
                ],
            }
        ],
    }


def _write_manifest(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "k8s-eso.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_k8s_eso_schema_is_packaged() -> None:
    schema = load_schema_for_family(K8S_ESO_FAMILY)

    assert schema["title"] == K8S_ESO_FAMILY
    assert schema["properties"]["schema"]["const"] == K8S_ESO_FAMILY
    assert "eso_stores" in schema["properties"]


def test_k8s_eso_validate_accepts_full_document() -> None:
    assert validate_manifest(_doc()) == K8S_ESO_FAMILY


def test_k8s_eso_loader_returns_typed_model() -> None:
    loaded = load_declarative_manifest_string(json.dumps(_doc()), suffix=".json")

    assert isinstance(loaded, K8sEsoManifestV1)
    assert loaded.eso_stores[0].name == "keeper-prod"
    assert loaded.external_secrets[0].data[0].property == "login"


def test_k8s_eso_schema_rejects_missing_data() -> None:
    document = _doc()
    del document["external_secrets"][0]["data"][0]["remote_key"]

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert exc.value.context["location"] == "external_secrets/0/data/0"
    assert "remote_key" in exc.value.reason


def test_k8s_eso_loader_rejects_unknown_store_ref() -> None:
    document = _doc()
    document["external_secrets"][0]["store_ref"] = "missing-store"

    with pytest.raises(SchemaError) as exc:
        load_k8s_eso_manifest(document)

    assert "unknown store_ref values" in exc.value.reason


def test_k8s_eso_loader_rejects_duplicate_store_names() -> None:
    document = _doc()
    document["eso_stores"].append(dict(document["eso_stores"][0]))

    with pytest.raises(SchemaError) as exc:
        load_k8s_eso_manifest(document)

    assert "duplicate eso_stores names" in exc.value.reason


def test_generate_cluster_secret_store_uses_keepersecurity_provider() -> None:
    manifest = load_k8s_eso_manifest(_doc())

    rendered = generate_cluster_secret_store(manifest.eso_stores[0])

    assert rendered == {
        "apiVersion": "external-secrets.io/v1",
        "kind": "ClusterSecretStore",
        "metadata": {"name": "keeper-prod"},
        "spec": {
            "provider": {
                "keepersecurity": {
                    "authRef": {
                        "name": "ksm-config-secret",
                        "key": "ksm_config",
                        "namespace": "external-secrets",
                    }
                }
            }
        },
    }


def test_generate_external_secret_maps_remote_refs() -> None:
    manifest = load_k8s_eso_manifest(_doc())

    rendered = generate_external_secret(manifest.external_secrets[0])

    assert rendered == {
        "apiVersion": "external-secrets.io/v1",
        "kind": "ExternalSecret",
        "metadata": {"name": "database-credentials"},
        "spec": {
            "secretStoreRef": {"name": "keeper-prod", "kind": "ClusterSecretStore"},
            "target": {"name": "database-credentials", "creationPolicy": "Owner"},
            "data": [
                {
                    "secretKey": "username",
                    "remoteRef": {"key": "ABC123", "property": "login"},
                },
                {
                    "secretKey": "password",
                    "remoteRef": {"key": "ABC123", "property": "password"},
                },
            ],
        },
    }


def test_generate_external_secret_omits_property_when_absent() -> None:
    document = _doc()
    del document["external_secrets"][0]["data"][0]["property"]
    manifest = load_k8s_eso_manifest(document)

    rendered = generate_external_secret(manifest.external_secrets[0])

    assert rendered["spec"]["data"][0]["remoteRef"] == {"key": "ABC123"}


def test_k8s_eso_plan_cli_exits_capability_error(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _doc())

    result = CliRunner().invoke(main, ["plan", str(path), "--json"], catch_exceptions=False)

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert K8S_ESO_FAMILY in result.output
    assert "upstream-gap" in result.output


def test_k8s_eso_apply_cli_exits_capability_error(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _doc())

    result = CliRunner().invoke(main, ["apply", str(path), "--dry-run"], catch_exceptions=False)

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert K8S_ESO_FAMILY in result.output
    assert "upstream-gap" in result.output
