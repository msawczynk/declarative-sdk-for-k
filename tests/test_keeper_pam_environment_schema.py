"""pam-environment.v1 live-proof schema annotation tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
_SCHEMA_PATH = _REPO / "keeper_sdk" / "core" / "schemas" / "pam-environment.v1.schema.json"
_MACHINE_EVIDENCE = "docs/live-proof/keeper-pam-environment.v1.89047920.machine.sanitized.json"


def _schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def test_pam_environment_live_proof_evidence_appends_machine_transcript() -> None:
    proof = _schema()["x-keeper-live-proof"]

    assert proof["status"] == "supported"
    assert proof["evidence"] == [
        "scripts/smoke/scenarios.py",
        _MACHINE_EVIDENCE,
    ]
    assert len(proof["evidence"]) == 2
    assert (_REPO / _MACHINE_EVIDENCE).is_file()
