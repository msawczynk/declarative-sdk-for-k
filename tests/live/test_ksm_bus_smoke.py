"""Live KSM bus smoke test.

Skipped unless:

  - ``KEEPER_LIVE_TENANT=1``
  - ``KEEPER_LIVE_BUS_RECORD_UID`` points at a KSM-visible writable record

The test writes only namespaced custom fields and deletes them in cleanup.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import UTC, datetime

import pytest

from keeper_sdk.cli._live.transcript import secret_leak_check
from keeper_sdk.secrets import KsmSecretStore
from keeper_sdk.secrets.bus import BusClient, KsmBus, VersionConflict


@pytest.mark.live(requires=("KEEPER_LIVE_BUS_RECORD_UID",))
def test_ksm_bus_live_write_read_ack_gc() -> None:
    record_uid = os.environ["KEEPER_LIVE_BUS_RECORD_UID"]
    config_path = (
        os.environ.get("KEEPER_LIVE_KSM_CONFIG")
        or os.environ.get("KEEPER_SDK_KSM_CONFIG")
        or os.environ.get("KSM_CONFIG")
        or None
    )
    nonce = uuid.uuid4().hex[:12]
    channel = f"live-smoke-{nonce}"
    sender_id = f"bus-sender-{nonce}"
    receiver_id = f"bus-receiver-{nonce}"
    channel_key = f"dsk.bus.channel.{channel}"
    cursor_key = f"dsk.bus.cursor.{channel}.{receiver_id}"
    cas_key = f"dsk.bus.cas.{nonce}"

    store = KsmSecretStore(config_path=config_path)
    bus = KsmBus(store, record_uid)
    sender = BusClient(store=store, directory_uid=record_uid, agent_id=sender_id, channel=channel)
    receiver = BusClient(
        store=store,
        directory_uid=record_uid,
        agent_id=receiver_id,
        channel=channel,
    )

    try:
        for key in (channel_key, cursor_key, cas_key):
            bus.delete(key)

        started = time.perf_counter()
        message_id = sender.send(
            to=receiver_id,
            subject="live-smoke",
            payload={"ok": True, "nonce": nonce},
            ttl_s=600,
            trace_id=nonce,
        )
        messages = receiver.receive()
        latency_ms = round((time.perf_counter() - started) * 1000)

        assert [message.id for message in messages] == [message_id]
        assert messages[0].payload == {"ok": True, "nonce": nonce}

        receiver.ack(last_id=message_id, consumer=receiver_id)
        assert receiver.receive(since_id=message_id) == []
        cursor = bus.get(cursor_key)
        assert cursor is not None
        assert cursor.value == {"consumer": receiver_id, "last_id": message_id}

        bus.publish(cas_key, {"step": "first", "nonce": nonce}, expected_version=0)
        cas_conflict_raised = False
        with pytest.raises(VersionConflict):
            bus.publish(cas_key, {"step": "second", "nonce": nonce}, expected_version=0)
        cas_conflict_raised = True

        expired_id = sender.send(
            to=receiver_id,
            subject="expired",
            payload={"expired": True, "nonce": nonce},
            ttl_s=-1,
        )
        removed = sender.gc(now=datetime.now(UTC))
        remaining_ids = {message.id for message in receiver.receive()}

        assert removed >= 1
        assert expired_id not in remaining_ids

        result = {
            "cas_conflict_raised": cas_conflict_raised,
            "gc_removed": removed,
            "latency_ms": latency_ms,
            "messages": len(messages),
        }
        rendered = json.dumps(result, sort_keys=True)
        leaks = secret_leak_check(
            rendered,
            env_keys=(
                "KEEPER_EMAIL",
                "KEEPER_PASSWORD",
                "KEEPER_TOTP_SECRET",
                "KEEPER_CONFIG",
                "KEEPER_LIVE_BUS_RECORD_UID",
                "KEEPER_LIVE_KSM_CONFIG",
                "KEEPER_SDK_KSM_CONFIG",
                "KSM_CONFIG",
            ),
        )
        assert leaks == [], f"sanitization leak: {leaks}"
        print(f"KSM_BUS_SMOKE {rendered}")
    finally:
        cleanup_store = KsmSecretStore(config_path=config_path)
        cleanup_bus = KsmBus(cleanup_store, record_uid)
        for key in (channel_key, cursor_key, cas_key):
            cleanup_bus.delete(key)
