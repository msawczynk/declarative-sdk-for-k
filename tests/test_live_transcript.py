"""Offline tests for the live-test transcript writer.

These tests run as part of the normal pytest suite — they DO NOT touch
a tenant. They exercise sanitization, schema shape, and leak-detection.
The actual live-tenant tests live in `tests/live/` and are skipped by
default; see `tests/live/conftest.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from keeper_sdk.cli._live.transcript import (
    Phase,
    Transcript,
    _fingerprint,
    _sanitize_value,
    secret_leak_check,
)


def test_sanitize_redacts_secret_keys() -> None:
    raw = {
        "username": "alice",
        "password": "hunter2",
        "config": "BEGIN PRIVATE KEY...",
        "nested": {"token": "abc", "ok": "fine"},
    }
    out = _sanitize_value(raw)
    assert out["password"] == "<redacted>"
    assert out["config"] == "<redacted>"
    assert out["nested"]["token"] == "<redacted>"
    assert out["username"] == "alice"
    assert out["nested"]["ok"] == "fine"


def test_sanitize_fingerprints_uid_strings() -> None:
    uid = "AbCdEfGhIjKlMnOpQrStUv"
    raw = {"keeper_uid": uid, "msg": f"created {uid}"}
    out = _sanitize_value(raw)
    assert uid not in json.dumps(out)
    assert out["keeper_uid"].startswith("<uid:")
    assert out["msg"].startswith("created <uid:")


def test_fingerprint_stable() -> None:
    assert _fingerprint("X" * 22) == _fingerprint("X" * 22)
    assert _fingerprint("a") != _fingerprint("b")


def test_transcript_to_dict_shape() -> None:
    t = Transcript(
        schema_family="pam-environment",
        schema_version="v1",
        commander_pin="89047920a0",
    )
    t.add_phase(Phase(name="bootstrap", status="ok", elapsed_ms=10))
    t.add_phase(Phase(name="login", status="failed", error="timeout"))
    t.finalize()
    d = t.to_dict()
    assert d["schema_family"] == "pam-environment"
    assert d["schema_version"] == "v1"
    assert d["commander_pin"] == "89047920a0"
    assert len(d["phases"]) == 2
    assert d["phases"][0]["status"] == "ok"
    assert d["phases"][1]["error"] == "timeout"
    assert d["summary"] == {"total_phases": 2, "ok": 1, "skipped": 0, "failed": 1}
    assert d["started_at"].endswith("Z")
    assert d["finished_at"].endswith("Z")


def test_transcript_write_then_leak_check_clean(tmp_path: Path) -> None:
    t = Transcript(
        schema_family="keeper-vault",
        schema_version="v1",
        commander_pin="abc1234",
    )
    t.add_phase(
        Phase(
            name="apply",
            status="ok",
            elapsed_ms=1234,
            details={"keeper_uid": "AbCdEfGhIjKlMnOpQrStUv", "rows": 3},
        )
    )
    out = tmp_path / "evidence.json"
    t.write(out)
    text = out.read_text()
    assert "AbCdEfGhIjKlMnOpQrStUv" not in text
    assert secret_leak_check(text) == []


def test_secret_leak_check_catches_pem() -> None:
    text = "phase ok\n-----BEGIN PRIVATE KEY-----\nxxx\n-----END PRIVATE KEY-----\n"
    warnings = secret_leak_check(text)
    assert any("PEM private-key" in w for w in warnings)


def test_secret_leak_check_catches_env_value(monkeypatch) -> None:
    monkeypatch.setenv("FAKE_SECRET", "S3cret-Value-Long-Enough")
    text = "phase ok value=S3cret-Value-Long-Enough\n"
    warnings = secret_leak_check(text, env_keys=("FAKE_SECRET",))
    assert any("FAKE_SECRET" in w for w in warnings)
