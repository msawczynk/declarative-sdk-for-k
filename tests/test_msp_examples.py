"""Schema-only validation of MSP example manifests (P1 parallel slice).

Independent of typed-model load (msp_models.py is owned by the P1 Composer
slice). Uses read_manifest_document + validate_manifest only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from keeper_sdk.core.manifest import read_manifest_document
from keeper_sdk.core.schema import validate_manifest

FIXTURES = Path(__file__).parent / "fixtures" / "examples" / "msp"


@pytest.mark.parametrize(
    "fixture_name",
    [
        "01-minimal-msp.yaml",
        "02-msp-with-addons.yaml",
        "03-multi-mc-msp.yaml",
    ],
)
def test_msp_example_validates_against_schema(fixture_name: str) -> None:
    document = read_manifest_document(FIXTURES / fixture_name)
    family = validate_manifest(document)
    assert family == "msp-environment.v1"


def test_minimal_has_empty_managed_companies() -> None:
    doc = read_manifest_document(FIXTURES / "01-minimal-msp.yaml")
    assert doc["managed_companies"] == []


def test_addons_fixture_uses_structured_shape() -> None:
    """Q6: addons must be structured {name, seats}, not bare strings."""
    doc = read_manifest_document(FIXTURES / "02-msp-with-addons.yaml")
    mc = doc["managed_companies"][0]
    for addon in mc["addons"]:
        assert isinstance(addon, dict)
        assert "name" in addon and isinstance(addon["name"], str)
        assert "seats" in addon and isinstance(addon["seats"], int)


def test_multi_mc_fixture_has_three_companies() -> None:
    doc = read_manifest_document(FIXTURES / "03-multi-mc-msp.yaml")
    assert len(doc["managed_companies"]) == 3
    names = [mc["name"] for mc in doc["managed_companies"]]
    assert names == ["Subsidiary A", "Subsidiary B", "Subsidiary C"]
