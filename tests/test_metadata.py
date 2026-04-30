"""Ownership metadata encode/decode."""

from __future__ import annotations

from keeper_sdk.core.metadata import (
    MANAGER_NAME,
    MARKER_VERSION,
    decode_marker,
    encode_marker,
    serialize_marker,
)


def test_encode_contains_required_fields() -> None:
    marker = encode_marker(uid_ref="x", manifest="env", resource_type="pamMachine")
    assert marker["manager"] == MANAGER_NAME
    assert marker["version"] == MARKER_VERSION
    assert marker["uid_ref"] == "x"
    assert marker["manifest"] == "env"
    assert marker["resource_type"] == "pamMachine"
    assert marker["parent_uid_ref"] is None
    assert marker["first_applied_at"] == marker["last_applied_at"]
    assert marker["applied_by"] == "commander/unknown"


def test_roundtrip() -> None:
    original = encode_marker(uid_ref="x", manifest="env", resource_type="pamMachine")
    raw = serialize_marker(original)
    decoded = decode_marker(raw)
    assert decoded == original


def test_decode_handles_empty() -> None:
    assert decode_marker(None) is None
    assert decode_marker("") is None
    assert decode_marker("not-json") is None


def test_foreign_marker_preserved() -> None:
    """Markers from other managers should still decode so diff can flag them."""
    data = decode_marker('{"manager":"someone-else","uid_ref":"x","version":"1"}')
    assert data is not None
    assert data["manager"] == "someone-else"
