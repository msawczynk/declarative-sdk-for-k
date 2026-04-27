"""keeper-ksm.v1 live-proof schema annotation tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from keeper_sdk.cli._live.transcript import secret_leak_check

_REPO = Path(__file__).resolve().parents[1]
_SCHEMA_PATH = (
    _REPO / "keeper_sdk" / "core" / "schemas" / "keeper-ksm" / "keeper-ksm.v1.schema.json"
)


def _schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def test_keeper_ksm_live_proof_status_supported() -> None:
    proof = _schema()["x-keeper-live-proof"]

    assert proof["status"] == "supported"
    assert proof["evidence"] == "docs/live-proof/keeper-ksm.v1.89047920.sanitized.json"
    assert "KsmLoginHelper" in proof["notes"]


def test_keeper_ksm_evidence_artifact_shape_and_leak_check() -> None:
    evidence = _REPO / _schema()["x-keeper-live-proof"]["evidence"]
    raw = evidence.read_text(encoding="utf-8")
    data = json.loads(raw)

    assert secret_leak_check(raw) == []
    assert data["family"] == "keeper-ksm.v1"
    assert data["scenario"] == "ksmLoginHelperBootstrapRoundTrip"
    assert data["commit"] == "8044bb89"
    assert data["commander_version"] == "17.2.13"
    assert isinstance(data["tenant_hash"], str)
    assert len(data["tenant_hash"]) == 8
    assert data["notes"]
    event_names = {event["event"] for event in data["events"]}
    assert {
        "bootstrap_ksm_application",
        "sample_fetch",
        "write_update",
        "fetch_back",
        "restore",
        "sanitization",
    } <= event_names
