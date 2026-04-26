"""Committed live-proof helpers (strict JSON, template invariants)."""

from __future__ import annotations

import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_LIVE_PROOF = _REPO / "docs" / "live-proof"


def test_vault_sanitized_template_is_strict_json() -> None:
    path = _LIVE_PROOF / "keeper-vault.v1.sanitized.template.json"
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data.get("template") is True
    assert data.get("family") == "keeper-vault.v1"


def test_docs_live_proof_json_files_parse() -> None:
    """Local mirror of CI ``schema-validate`` RFC 8259 check for this directory."""
    if not _LIVE_PROOF.is_dir():
        return
    for path in sorted(_LIVE_PROOF.glob("*.json")):
        json.loads(path.read_text(encoding="utf-8"))
