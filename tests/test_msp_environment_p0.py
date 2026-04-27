"""P0 tests for msp-environment.v1 (registry + JSON Schema; no plan/apply)."""

from __future__ import annotations

import pytest

import keeper_sdk.core.schema as schema_module
from keeper_sdk.core import SchemaError, validate_manifest
from keeper_sdk.core.schema import SCHEMA_RESOURCE_BY_FAMILY, load_schema_for_family


@pytest.fixture(autouse=True)
def _clear_schema_cache() -> None:
    schema_module.load_schema_for_family.cache_clear()
    yield
    schema_module.load_schema_for_family.cache_clear()


def test_msp_family_registered() -> None:
    assert "msp-environment.v1" in SCHEMA_RESOURCE_BY_FAMILY
    assert (
        SCHEMA_RESOURCE_BY_FAMILY["msp-environment.v1"]
        == "msp-environment/msp-environment.v1.schema.json"
    )


def test_msp_schema_loads() -> None:
    blob = load_schema_for_family("msp-environment.v1")
    proof = blob.get("x-keeper-live-proof")
    assert isinstance(proof, dict)
    assert proof.get("status") == "scaffold-only"


def test_msp_minimal_manifest_validates() -> None:
    fam = validate_manifest(
        {
            "schema": "msp-environment.v1",
            "name": "lab-msp",
            "managed_companies": [],
        }
    )
    assert fam == "msp-environment.v1"


def test_msp_with_one_mc_validates() -> None:
    validate_manifest(
        {
            "schema": "msp-environment.v1",
            "name": "lab-msp",
            "managed_companies": [
                {"name": "Acme MC", "plan": "business", "seats": 10},
            ],
        }
    )


def test_msp_addon_structured_required() -> None:
    with pytest.raises(SchemaError) as exc:
        validate_manifest(
            {
                "schema": "msp-environment.v1",
                "name": "x",
                "managed_companies": [
                    {
                        "name": "A",
                        "plan": "business",
                        "seats": 1,
                        "addons": ["rbi"],
                    }
                ],
            }
        )
    assert "manifest failed schema" in exc.value.reason


def test_msp_negative_seats_rejected() -> None:
    with pytest.raises(SchemaError):
        validate_manifest(
            {
                "schema": "msp-environment.v1",
                "name": "x",
                "managed_companies": [
                    {"name": "A", "plan": "business", "seats": -1},
                ],
            }
        )


def test_msp_unknown_top_level_key_rejected() -> None:
    with pytest.raises(SchemaError):
        validate_manifest(
            {
                "schema": "msp-environment.v1",
                "name": "x",
                "managed_companies": [],
                "extra_key": 1,
            }
        )


def test_msp_duplicate_mc_names_rejected() -> None:
    with pytest.raises(SchemaError) as exc:
        validate_manifest(
            {
                "schema": "msp-environment.v1",
                "name": "x",
                "managed_companies": [
                    {"name": "Same", "plan": "business", "seats": 1},
                    {"name": "Same", "plan": "enterprise", "seats": 2},
                ],
            }
        )
    assert "duplicate" in exc.value.reason.lower()
