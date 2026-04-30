"""Validation coverage for root ``examples/*.yaml`` manifests."""

from __future__ import annotations

from pathlib import Path

import pytest

from keeper_sdk.core.manifest import read_manifest_document
from keeper_sdk.core.schema import validate_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"
EXAMPLE_MANIFESTS: tuple[Path, ...] = tuple(sorted(EXAMPLES_DIR.glob("*.yaml")))


def _example_id(manifest_path: Path) -> str:
    return manifest_path.name


def test_root_examples_exist() -> None:
    assert len(EXAMPLE_MANIFESTS) >= 10


@pytest.mark.parametrize("manifest_path", EXAMPLE_MANIFESTS, ids=_example_id)
def test_root_example_validate_manifest_succeeds(manifest_path: Path) -> None:
    document = read_manifest_document(manifest_path)

    family = validate_manifest(document)

    assert family
