from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from keeper_sdk.secrets import KsmSecretStore
from keeper_sdk.secrets.bus import KsmAgentBus, KsmBus, MockBusStore
from tests._fakes.ksm import FakeRecord, install_fake_ksm_core


def _config_file(tmp_path: Path) -> Path:
    path = tmp_path / "ksm-config.json"
    path.write_text("{}", encoding="utf-8")
    return path


def _store(tmp_path: Path) -> KsmSecretStore:
    return KsmSecretStore(config_path=_config_file(tmp_path))


def _mock_custom_value(store: MockBusStore, slot: str, label: str) -> str | None:
    for field in store.get_record(slot).dict["custom"]:
        if field.get("label") == label:
            values = field.get("value") or []
            return values[0] if values else None
    return None


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_put_creates_custom_field_and_get_reads_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    uid = "BUSUID123456"
    record = FakeRecord(uid=uid, custom=[])
    fake_ksm = install_fake_ksm_core(monkeypatch, {uid: record})
    saved: list[str] = []

    def save(self: Any, saved_record: FakeRecord) -> bool:
        _ = self
        saved.append(saved_record.uid)
        return True

    monkeypatch.setattr(fake_ksm, "save", save, raising=False)
    bus = KsmBus(_store(tmp_path), uid)

    bus.put("phase7.status", "ready")

    assert bus.get("phase7.status") == "ready"
    assert record.dict["custom"] == [{"type": "text", "label": "phase7.status", "value": ["ready"]}]
    assert saved == [uid]


def test_put_updates_existing_custom_field_without_duplicate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    uid = "BUSUID123456"
    record = FakeRecord(
        uid=uid,
        custom=[
            {"type": "text", "label": "phase7.status", "value": ["starting"]},
            {"type": "text", "label": "other", "value": ["keep"]},
        ],
    )
    install_fake_ksm_core(monkeypatch, {uid: record})
    bus = KsmBus(_store(tmp_path), uid)

    bus.put("phase7.status", "done")

    assert bus.get("phase7.status") == "done"
    assert record.dict["custom"] == [
        {"type": "text", "label": "phase7.status", "value": ["done"]},
        {"type": "text", "label": "other", "value": ["keep"]},
    ]


def test_get_missing_key_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    uid = "BUSUID123456"
    install_fake_ksm_core(
        monkeypatch,
        {uid: FakeRecord(uid=uid, custom=[{"type": "text", "label": "known", "value": ["v"]}])},
    )

    assert KsmBus(_store(tmp_path), uid).get("missing") is None


def test_missing_record_uid_keeps_not_implemented_fallback(tmp_path: Path) -> None:
    bus = KsmBus(_store(tmp_path), "")

    with pytest.raises(NotImplementedError, match="next_action"):
        bus.put("phase7.status", "ready")

    with pytest.raises(NotImplementedError, match="next_action"):
        bus.get("phase7.status")


def test_agent_bus_acquire_when_empty_returns_true() -> None:
    store = MockBusStore()
    bus = KsmAgentBus(store)

    assert bus.acquire("slot-a", "worker-a", 60) is True
    assert _mock_custom_value(store, "slot-a", "_bus_holder") == "worker-a"
    assert _mock_custom_value(store, "slot-a", "_bus_expiry") is not None


def test_agent_bus_acquire_when_held_and_not_expired_returns_false() -> None:
    bus = KsmAgentBus(MockBusStore())

    assert bus.acquire("slot-a", "worker-a", 60) is True

    assert bus.acquire("slot-a", "worker-b", 60) is False


def test_agent_bus_acquire_when_expired_takes_over() -> None:
    store = MockBusStore()
    bus = KsmAgentBus(store)

    assert bus.acquire("slot-a", "worker-a", -1) is True

    assert bus.acquire("slot-a", "worker-b", 60) is True
    assert _mock_custom_value(store, "slot-a", "_bus_holder") == "worker-b"


def test_agent_bus_release_checks_holder() -> None:
    store = MockBusStore()
    bus = KsmAgentBus(store)
    assert bus.acquire("slot-a", "worker-a", 60) is True

    assert bus.release("slot-a", "worker-b") is False
    assert _mock_custom_value(store, "slot-a", "_bus_holder") == "worker-a"

    assert bus.release("slot-a", "worker-a") is True
    assert _mock_custom_value(store, "slot-a", "_bus_holder") is None


def test_agent_bus_publish_consume_round_trip() -> None:
    bus = KsmAgentBus(MockBusStore())
    assert bus.acquire("slot-a", "worker-a", 60) is True
    payload = {"step": "apply", "ok": True}

    bus.publish("slot-a", payload, "worker-a")

    assert bus.consume("slot-a") == payload
    assert bus.consume("slot-a") is None
    assert bus.acquire("slot-a", "worker-b", 60) is True


def test_agent_bus_ping_renews_ttl() -> None:
    store = MockBusStore()
    bus = KsmAgentBus(store)
    assert bus.acquire("slot-a", "worker-a", 60) is True
    before = _parse_iso(_mock_custom_value(store, "slot-a", "_bus_expiry") or "")

    assert bus.ping("slot-a") is True

    after = _parse_iso(_mock_custom_value(store, "slot-a", "_bus_expiry") or "")
    assert after > before

    assert bus.release("slot-a", "worker-a") is True
    assert bus.ping("slot-a") is False
