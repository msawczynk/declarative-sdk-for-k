"""P1 tests for msp-environment.v1 typed models and declarative load."""

from __future__ import annotations

import textwrap

import pytest
from pydantic import ValidationError

import keeper_sdk.core.schema as schema_module
from keeper_sdk.core import UnsupportedFamilyError
from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.manifest import (
    load_declarative_manifest,
    load_declarative_manifest_string,
)
from keeper_sdk.core.msp_models import (
    MSP_FAMILY,
    Addon,
    MspManifestV1,
    load_msp_manifest,
)


@pytest.fixture(autouse=True)
def _clear_schema_cache() -> None:
    schema_module.load_schema_for_family.cache_clear()
    yield
    schema_module.load_schema_for_family.cache_clear()


def test_minimal_manifest_round_trip() -> None:
    doc = {
        "schema": "msp-environment.v1",
        "name": "lab",
        "managed_companies": [],
    }
    m = MspManifestV1.model_validate(doc)
    assert m.msp_schema == MSP_FAMILY
    assert m.name == "lab"
    assert m.managed_companies == []


def test_one_mc_round_trip() -> None:
    doc = {
        "schema": "msp-environment.v1",
        "name": "one",
        "managed_companies": [
            {
                "name": "Acme",
                "plan": "enterprise",
                "seats": 3,
                "addons": [
                    {"name": "connection_manager", "seats": 2},
                ],
            }
        ],
    }
    m = MspManifestV1.model_validate(doc)
    out = m.model_dump(mode="json", exclude_none=True, by_alias=True)
    m2 = MspManifestV1.model_validate(out)
    assert m2.managed_companies[0].addons[0] == Addon(name="connection_manager", seats=2)


def test_addons_must_be_structured() -> None:
    with pytest.raises(ValidationError):
        MspManifestV1.model_validate(
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


def test_seats_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        MspManifestV1.model_validate(
            {
                "schema": "msp-environment.v1",
                "name": "x",
                "managed_companies": [
                    {"name": "A", "plan": "business", "seats": -1},
                ],
            }
        )


def test_load_msp_manifest_wraps_validation_error() -> None:
    # JSON Schema accepts `name: "   "`; Pydantic strip + min_length makes it invalid.
    with pytest.raises(SchemaError) as exc:
        load_msp_manifest(
            {
                "schema": "msp-environment.v1",
                "name": "x",
                "managed_companies": [
                    {"name": "   ", "plan": "business", "seats": 0},
                ],
            }
        )
    assert isinstance(exc.value.__cause__, ValidationError)


def test_load_msp_manifest_rejects_case_insensitive_duplicate_mc_names() -> None:
    with pytest.raises(SchemaError) as exc:
        load_msp_manifest(
            {
                "schema": "msp-environment.v1",
                "name": "x",
                "managed_companies": [
                    {"name": "Acme", "plan": "business", "seats": 1},
                    {"name": "acme", "plan": "enterprise", "seats": 2},
                ],
            }
        )

    assert "duplicate name case-insensitively" in exc.value.reason
    assert (
        exc.value.next_action
        == "rename one managed_company; names must be unique case-insensitively"
    )


def test_load_msp_manifest_via_load_declarative_manifest(tmp_path) -> None:
    p = tmp_path / "m.yaml"
    p.write_text(
        textwrap.dedent(
            """
            schema: msp-environment.v1
            name: via-loader
            managed_companies: []
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    m = load_declarative_manifest(p)
    assert isinstance(m, MspManifestV1)
    assert m.name == "via-loader"


def test_round_trip_section_4_examples(tmp_path) -> None:
    # §4.1 — as in docs/MSP_FAMILY_DESIGN.md
    y1 = (
        textwrap.dedent(
            """
        schema: msp-environment.v1
        name: msp-baseline
        managed_companies:
          - name: "Contoso East"
            plan: business
            seats: 5
        """
        ).strip()
        + "\n"
    )
    # §4.2 — memo uses `connection_manager:5` list entries (not Q6 / JSON Schema);
    # structured form below matches intent + schema.
    y2 = (
        textwrap.dedent(
            """
        schema: msp-environment.v1
        name: msp-with-addons
        managed_companies:
          - name: "Fabrikam Managed"
            plan: enterprise
            seats: 25
            file_plan: enterprise
            addons:
              - name: connection_manager
                seats: 5
              - name: remote_browser_isolation
                seats: 5
        """
        ).strip()
        + "\n"
    )
    # §4.3 as written uses seats: -1 and `node` (not in P0 schema); adapted for schema validity.
    y3 = (
        textwrap.dedent(
            """
        schema: msp-environment.v1
        name: msp-noded
        managed_companies:
          - name: "Adatum Corp"
            plan: business
            seats: 0
            file_plan: null
            addons: []
        """
        ).strip()
        + "\n"
    )

    for i, (raw, want_name) in enumerate(
        [
            (y1, "msp-baseline"),
            (y2, "msp-with-addons"),
            (y3, "msp-noded"),
        ],
        start=1,
    ):
        p = tmp_path / f"ex{i}.yaml"
        p.write_text(raw, encoding="utf-8")
        m = load_declarative_manifest(p)
        assert isinstance(m, MspManifestV1)
        assert m.name == want_name
        r0 = m.managed_companies[0]
        assert r0.name
        assert r0.seats >= 0
        if i == 2:
            assert {a.name for a in (r0.addons or [])} == {
                "connection_manager",
                "remote_browser_isolation",
            }
        dumped = m.model_dump(mode="json", exclude_none=True, by_alias=True)
        m2 = MspManifestV1.model_validate(dumped)
        assert m2.name == want_name


def test_unsupported_family_message_includes_msp() -> None:
    with pytest.raises(UnsupportedFamilyError) as exc:
        load_declarative_manifest_string('{"schema": "keeper-ksm.v1"}', suffix=".json")
    assert "msp-environment.v1" in exc.value.reason
