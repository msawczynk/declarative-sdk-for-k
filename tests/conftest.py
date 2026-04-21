"""Shared fixtures. Reuse the authoritative manifest examples shipped in
``keeper-pam-declarative/examples/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = _REPO_ROOT / "keeper-pam-declarative" / "examples"


@pytest.fixture(scope="session")
def examples_dir() -> Path:
    assert EXAMPLES.is_dir(), f"examples folder not found: {EXAMPLES}"
    return EXAMPLES


@pytest.fixture
def minimal_manifest_path(examples_dir: Path) -> Path:
    return examples_dir / "minimal" / "environment.yaml"


@pytest.fixture
def full_local_manifest_path(examples_dir: Path) -> Path:
    return examples_dir / "full-local" / "environment.yaml"


@pytest.fixture
def aws_manifest_path(examples_dir: Path) -> Path:
    return examples_dir / "aws-iam-rotation" / "environment.yaml"


@pytest.fixture
def domain_manifest_path(examples_dir: Path) -> Path:
    return examples_dir / "domain-rotation" / "environment.yaml"


@pytest.fixture
def invalid_manifest(examples_dir: Path):
    def _pick(name: str) -> Path:
        return examples_dir / "invalid" / name
    return _pick
