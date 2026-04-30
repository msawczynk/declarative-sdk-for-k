from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from keeper_sdk.secrets import KsmSecretStore
from keeper_sdk.secrets.bus import BusClient, KsmBus, VersionConflict
from tests._fakes.ksm import FakeRecord, install_fake_ksm_core


def _config_file(tmp_path: Path) -> Path:
    path = tmp_path / "ksm-config.json"
    path.write_text("{}", encoding="utf-8")
    return path


def _store(tmp_path: Path) -> KsmSecretStore:
    return KsmSecretStore(config_path=_config_file(tmp_path))


def _install_bus(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    record: FakeRecord | None = None,
) -> tuple[KsmBus, FakeRecord, list[str]]:
    bus_record = record or FakeRecord(uid="BUSUID123456", custom=[])
    fake_ksm = install_fake_ksm_core(monkeypatch, {bus_record.uid: bus_record})
    saved: list[str] = []

    def save(self: Any, saved_record: FakeRecord) -> bool:
        _ = self
        saved.append(saved_record.uid)
        return True

    monkeypatch.setattr(fake_ksm, "save", save, raising=False)
    return KsmBus(_store(tmp_path), bus_record.uid), bus_record, saved


def _field_payload(record: FakeRecord, key: str) -> dict[str, Any]:
    for field in record.dict["custom"]:
        if field["label"] == key:
            return json.loads(field["value"][0])
    raise AssertionError(f"missing field {key}")


def test_publish_creates_field(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bus, record, saved = _install_bus(monkeypatch, tmp_path)

    version = bus.publish("phase.status", {"state": "ready"}, expected_version=0)

    payload = _field_payload(record, "phase.status")
    assert version == 1
    assert payload["schema"] == "keeper-sdk.ksm-bus.v1"
    assert payload["version"] == 1
    assert payload["value"] == {"state": "ready"}
    assert saved == [record.uid]


def test_publish_cas_conflict_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bus, _record, _saved = _install_bus(monkeypatch, tmp_path)
    bus.publish("phase.status", "ready", expected_version=0)

    with pytest.raises(VersionConflict) as exc_info:
        bus.publish("phase.status", "done", expected_version=0)

    assert exc_info.value.key == "phase.status"
    assert exc_info.value.expected_version == 0
    assert exc_info.value.actual_version == 1


def test_subscribe_yields_on_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bus, _record, _saved = _install_bus(monkeypatch, tmp_path)
    bus.publish("phase.status", "ready", expected_version=0)
    subscription = bus.subscribe("phase.status", poll_interval=0)

    assert next(subscription) == ("ready", 1)
    bus.publish("phase.status", "done", expected_version=1)

    assert next(subscription) == ("done", 2)


def test_get_returns_version(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bus, _record, _saved = _install_bus(monkeypatch, tmp_path)
    bus.publish("phase.status", "ready", expected_version=0)

    result = bus.get("phase.status")

    assert result == ("ready", 1)
    assert result is not None
    assert result.value == "ready"
    assert result.version == 1


def test_delete_removes_field(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bus, record, saved = _install_bus(monkeypatch, tmp_path)
    bus.publish("phase.status", "ready", expected_version=0)

    bus.delete("phase.status")

    assert record.dict["custom"] == []
    assert bus.get("phase.status") is None
    assert saved == [record.uid, record.uid]


def test_bus_client_send_receive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bus, record, _saved = _install_bus(monkeypatch, tmp_path)
    sender = BusClient(store=bus._store, directory_uid=record.uid, agent_id="worker-a")
    receiver = BusClient(store=bus._store, directory_uid=record.uid, agent_id="worker-b")

    message_id = sender.send(to="worker-b", subject="status", payload={"ok": True})
    messages = receiver.receive()

    assert [message.id for message in messages] == [message_id]
    assert messages[0].sender == "worker-a"
    assert messages[0].payload == {"ok": True}


def test_bus_client_multi_agent_ordering(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bus, record, _saved = _install_bus(monkeypatch, tmp_path)
    worker_a = BusClient(store=bus._store, directory_uid=record.uid, agent_id="worker-a")
    worker_c = BusClient(store=bus._store, directory_uid=record.uid, agent_id="worker-c")
    worker_b = BusClient(store=bus._store, directory_uid=record.uid, agent_id="worker-b")

    first = worker_a.send(to="worker-b", subject="step", payload={"n": 1})
    second = worker_a.send(to="worker-b", subject="step", payload={"n": 2})
    third = worker_c.send(to="worker-b", subject="step", payload={"n": 3})

    messages = worker_b.receive()
    assert [message.id for message in messages] == sorted([first, second, third])
    assert [message.payload["n"] for message in messages] == [1, 2, 3]


def test_publish_expected_zero_creates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bus, _record, _saved = _install_bus(monkeypatch, tmp_path)

    assert bus.publish("phase.status", "ready", expected_version=0) == 1


def test_publish_without_expected_overwrites(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bus, _record, _saved = _install_bus(monkeypatch, tmp_path)
    bus.publish("phase.status", "ready", expected_version=0)

    assert bus.publish("phase.status", "done") == 2
    assert bus.get("phase.status") == ("done", 2)


def test_get_missing_returns_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bus, _record, _saved = _install_bus(monkeypatch, tmp_path)

    assert bus.get("missing") is None


def test_delete_missing_key_noop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bus, record, saved = _install_bus(monkeypatch, tmp_path)

    bus.delete("missing")

    assert record.dict["custom"] == []
    assert saved == []


def test_publish_rejects_empty_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bus, _record, _saved = _install_bus(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="key"):
        bus.publish("", "ready")


def test_bus_client_filters_recipient(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bus, record, _saved = _install_bus(monkeypatch, tmp_path)
    sender = BusClient(store=bus._store, directory_uid=record.uid, agent_id="worker-a")
    worker_b = BusClient(store=bus._store, directory_uid=record.uid, agent_id="worker-b")

    sender.send(to="worker-b", subject="status", payload="for-b")
    sender.send(to="worker-c", subject="status", payload="for-c")
    sender.send(to="*", subject="broadcast", payload="all")

    assert [message.payload for message in worker_b.receive()] == ["for-b", "all"]


def test_bus_client_channel_separation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bus, record, _saved = _install_bus(monkeypatch, tmp_path)
    sender = BusClient(store=bus._store, directory_uid=record.uid, agent_id="worker-a")
    receiver = BusClient(store=bus._store, directory_uid=record.uid, agent_id="worker-b")

    sender.send(to="worker-b", subject="status", payload="alpha", channel="alpha")
    sender.send(to="worker-b", subject="status", payload="beta", channel="beta")

    assert [message.payload for message in receiver.receive(channel="alpha")] == ["alpha"]
    assert [message.payload for message in receiver.receive(channel="beta")] == ["beta"]


def test_bus_client_ack_writes_cursor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bus, record, _saved = _install_bus(monkeypatch, tmp_path)
    client = BusClient(store=bus._store, directory_uid=record.uid, agent_id="worker-b")

    client.ack(last_id="00000000000000000001-abc", consumer="worker-b")

    cursor = bus.get("dsk.bus.cursor.default.worker-b")
    assert cursor == ({"consumer": "worker-b", "last_id": "00000000000000000001-abc"}, 1)


def test_bus_client_gc_removes_expired(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bus, record, _saved = _install_bus(monkeypatch, tmp_path)
    client = BusClient(store=bus._store, directory_uid=record.uid, agent_id="worker-a")
    client.send(to="worker-b", subject="status", payload="expired", ttl_s=-1)
    client.send(to="worker-b", subject="status", payload="fresh", ttl_s=3600)

    removed = client.gc(now=datetime.now(UTC))

    assert removed == 1
    remaining = BusClient(store=bus._store, directory_uid=record.uid, agent_id="worker-b").receive()
    assert [message.payload for message in remaining] == ["fresh"]


def test_legacy_put_value_is_still_readable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bus, _record, _saved = _install_bus(monkeypatch, tmp_path)

    bus.put("phase.status", "ready")

    assert bus.get("phase.status") == "ready"
    assert bus.get("phase.status") == ("ready", 0)
