"""Shared fixtures. Reuse the authoritative manifest examples shipped in
``keeper-pam-declarative/examples/``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Example manifests intentionally exercise rotation/JIT/etc. to pin the
# full intended surface for forward-compatibility tests. The SDK's
# preview gate (see ``keeper_sdk.core.preview``) would reject them at
# load time; enable preview by default for the test suite and let
# individual tests clear the variable when they assert the gate.
os.environ.setdefault("DSK_PREVIEW", "1")

# Preferred: vendored copy inside the repo (ships with the package for
# CI + contributors who don't check out the upstream declarative repo).
# Fallback: sibling checkout — convenient for local development where
# both repos sit under the same parent so edits in one show up in the
# other without re-copying.
_VENDORED = Path(__file__).resolve().parent / "fixtures" / "examples"
_SIBLING = Path(__file__).resolve().parents[2] / "keeper-pam-declarative" / "examples"
EXAMPLES = _VENDORED if _VENDORED.is_dir() else _SIBLING


@pytest.fixture(scope="session")
def examples_dir() -> Path:
    assert EXAMPLES.is_dir(), f"examples folder not found: {EXAMPLES}"
    return EXAMPLES


@pytest.fixture
def minimal_manifest_path(examples_dir: Path) -> Path:
    return examples_dir / "minimal" / "environment.yaml"


@pytest.fixture
def pam_db_overlay_manifest_path(examples_dir: Path) -> Path:
    return examples_dir / "diff-pamdb-overlay" / "environment.yaml"


@pytest.fixture
def pam_dir_overlay_manifest_path(examples_dir: Path) -> Path:
    return examples_dir / "diff-pamdir-overlay" / "environment.yaml"


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
