"""Alias canonicalization + pam_import round-trip."""

from __future__ import annotations

from pathlib import Path

from keeper_sdk.core import load_manifest, to_pam_import_json
from keeper_sdk.core.normalize import canonicalize


def test_alias_rewrite() -> None:
    doc = {
        "resources": [
            {
                "hostname": "x",
                "pam_config": "cfg-a",
                "pam_settings": {
                    "connection": {
                        "administrative_credentials": "admin",
                    }
                },
            }
        ]
    }
    out = canonicalize(doc)
    resource = out["resources"][0]
    assert resource["host"] == "x"
    assert resource["pam_configuration_uid_ref"] == "cfg-a"
    assert resource["pam_settings"]["connection"]["administrative_credentials_uid_ref"] == "admin"


def test_to_pam_import_rewrites_refs_to_titles(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    doc = manifest.model_dump(mode="python", exclude_none=True)
    converted = to_pam_import_json(doc)

    resource = converted["pam_data"]["resources"][0]
    assert "uid_ref" not in resource
    assert resource["pam_configuration"] == "Acme Lab Local PAM Configuration"
    connection = resource["pam_settings"]["connection"]
    assert connection["administrative_credentials"] == "lab-linux-1-root"


def test_to_pam_import_preserves_top_metadata(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    doc = manifest.model_dump(mode="python", exclude_none=True)
    converted = to_pam_import_json(doc)
    assert converted["project"] == manifest.name
    assert "name" not in converted
    assert "pam_configuration" in converted
    assert "pam_data" in converted
