"""keeper-integrations-identity.v1 offline schema, model, diff, and CLI tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CAPABILITY
from keeper_sdk.core import IDENTITY_FAMILY, IdentityManifestV1, load_schema_for_family
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.integrations_identity_diff import compute_identity_diff
from keeper_sdk.core.manifest import load_declarative_manifest_string
from keeper_sdk.core.models_integrations_identity import load_identity_manifest
from keeper_sdk.core.schema import validate_manifest


def _minimal_doc() -> dict[str, Any]:
    return {
        "schema": IDENTITY_FAMILY,
        "domains": [{"name": "acme.example.com"}],
    }


def _full_doc() -> dict[str, Any]:
    return {
        "schema": IDENTITY_FAMILY,
        "domains": [
            {"name": "acme.example.com", "verified": True, "primary": True},
            {"name": "login.example.com", "verified": False, "primary": False},
        ],
        "scim": [
            {
                "name": "Okta SCIM",
                "uid_ref": "scim.okta",
                "provider": "okta",
                "sync_groups": True,
                "base_url": "https://acme.okta.com/scim/v2",
                "token_uid_ref": "keeper-vault:records:rec.scim_token",
            }
        ],
        "sso_providers": [
            {
                "name": "Primary SAML",
                "uid_ref": "sso.primary",
                "type": "saml",
                "entity_id": "https://sso.acme.example.com/saml",
                "metadata_url": "https://sso.acme.example.com/metadata.xml",
                "default_role_uid_ref": "keeper-enterprise:roles:role.employee",
            }
        ],
        "outbound_email": {
            "from_address": "no-reply@acme.example.com",
            "reply_to": "it@acme.example.com",
            "smtp_uid_ref": "keeper-vault:records:rec.smtp",
        },
    }


def _manifest(document: dict[str, Any] | None = None) -> IdentityManifestV1:
    return load_identity_manifest(document or _full_doc())


def _write_manifest(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "identity.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_identity_v1_schema_is_packaged_under_integrations_path() -> None:
    schema = load_schema_for_family(IDENTITY_FAMILY)

    assert schema["title"] == IDENTITY_FAMILY
    assert "scim" in schema["properties"]


def test_identity_v1_validate_minimal_one_domain() -> None:
    assert validate_manifest(_minimal_doc()) == IDENTITY_FAMILY


def test_identity_v1_validate_full() -> None:
    assert validate_manifest(_full_doc()) == IDENTITY_FAMILY


def test_identity_v1_invalid_missing_required_domain_name() -> None:
    document = _minimal_doc()
    del document["domains"][0]["name"]

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert exc.value.context["location"] == "domains/0"
    assert "name" in exc.value.reason


def test_identity_v1_invalid_missing_required_scim_token_ref() -> None:
    document = _full_doc()
    del document["scim"][0]["token_uid_ref"]

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert exc.value.context["location"] == "scim/0"
    assert "token_uid_ref" in exc.value.reason


def test_identity_v1_invalid_scim_provider_enum() -> None:
    document = _full_doc()
    document["scim"][0]["provider"] = "adfs"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "not one of" in exc.value.reason


def test_identity_v1_invalid_sso_type_enum() -> None:
    document = _full_doc()
    document["sso_providers"][0]["type"] = "oauth"

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "not one of" in exc.value.reason


def test_identity_v1_rejects_unknown_property() -> None:
    document = _minimal_doc()
    document["domains"][0]["extra"] = True

    with pytest.raises(SchemaError) as exc:
        validate_manifest(document)

    assert "Additional properties" in exc.value.reason


def test_identity_loader_returns_typed_model() -> None:
    loaded = load_declarative_manifest_string(json.dumps(_minimal_doc()), suffix=".json")

    assert isinstance(loaded, IdentityManifestV1)
    assert loaded.domains[0].verified is False


def test_identity_manifest_roundtrip() -> None:
    manifest = _manifest()
    dumped = manifest.model_dump(mode="json", exclude_none=True, by_alias=True)
    loaded = load_declarative_manifest_string(json.dumps(dumped), suffix=".json")

    assert isinstance(loaded, IdentityManifestV1)
    assert loaded.model_dump(mode="json", exclude_none=True, by_alias=True) == dumped


def test_identity_loader_rejects_duplicate_uid_refs() -> None:
    document = _full_doc()
    document["sso_providers"][0]["uid_ref"] = "scim.okta"

    with pytest.raises(SchemaError) as exc:
        load_identity_manifest(document)

    assert "duplicate uid_ref" in exc.value.reason


def test_identity_loader_rejects_duplicate_domain_names() -> None:
    document = _minimal_doc()
    document["domains"].append({"name": "ACME.example.com"})

    with pytest.raises(SchemaError) as exc:
        load_identity_manifest(document)

    assert "duplicate domain names" in exc.value.reason


def test_identity_diff_detects_domain_add() -> None:
    row = next(
        change
        for change in compute_identity_diff(_manifest(_minimal_doc()), {"domains": []})
        if change.resource_type == "identity_domain"
    )

    assert row.kind is ChangeKind.CREATE
    assert row.uid_ref == "acme.example.com"
    assert row.after["name"] == "acme.example.com"


def test_identity_diff_detects_scim_provider_change() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["scim"][0]["provider"] = "azure"

    row = next(
        change for change in compute_identity_diff(desired, live) if change.uid_ref == "scim.okta"
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.before == {"provider": "azure"}
    assert row.after == {"provider": "okta"}


def test_identity_diff_detects_sso_metadata_url_change() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["sso_providers"][0]["metadata_url"] = "https://old.example.com/metadata.xml"

    row = next(
        change for change in compute_identity_diff(desired, live) if change.uid_ref == "sso.primary"
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.before == {"metadata_url": "https://old.example.com/metadata.xml"}
    assert row.after == {"metadata_url": "https://sso.acme.example.com/metadata.xml"}


def test_identity_diff_detects_outbound_email_change() -> None:
    desired = _manifest()
    live = desired.model_dump(mode="python", exclude_none=True, by_alias=True)
    live["outbound_email"]["reply_to"] = "old-it@acme.example.com"

    row = next(
        change
        for change in compute_identity_diff(desired, live)
        if change.resource_type == "identity_outbound_email"
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.before == {"reply_to": "old-it@acme.example.com"}
    assert row.after == {"reply_to": "it@acme.example.com"}


def test_identity_diff_noops_matching_snapshot() -> None:
    manifest = _manifest()
    live = manifest.model_dump(mode="python", exclude_none=True, by_alias=True)

    changes = compute_identity_diff(manifest, live)

    assert {change.kind for change in changes} == {ChangeKind.NOOP}


def test_identity_validate_cli_is_schema_only(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _minimal_doc())

    result = CliRunner().invoke(main, ["validate", str(path), "--json"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["family"] == IDENTITY_FAMILY
    assert payload["mode"] == "schema_only"


def test_identity_plan_cli_exits_capability_error(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _minimal_doc())

    result = CliRunner().invoke(main, ["plan", str(path), "--json"], catch_exceptions=False)

    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert "plan/apply is upstream-gap" in result.output
