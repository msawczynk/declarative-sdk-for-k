"""KSM-backed inter-agent bus helpers.

``KsmBus`` stores low-volume coordination state in custom text fields on one
Keeper Secrets Manager record. ``publish`` writes a JSON envelope that carries
the caller's value plus a monotonically increasing version, and accepts an
``expected_version`` guard for compare-and-swap style updates.

``BusClient`` layers ordered channel messages on top of ``KsmBus``. It is
intended for small agent handoffs, not high-throughput queues: KSM remains the
source of persistence and audit, while CAS keeps concurrent writers from
silently overwriting each other when both clients have fresh readback.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, NoReturn

from keeper_sdk.core.errors import CapabilityError

if TYPE_CHECKING:
    from keeper_sdk.secrets.ksm import KsmSecretStore


_BUS_FIELD_TYPE = "text"
_BUS_SCHEMA = "keeper-sdk.ksm-bus.v1"
_BUS_CHANNEL_PREFIX = "dsk.bus.channel."
_BUS_CURSOR_PREFIX = "dsk.bus.cursor."
_DEFAULT_CHANNEL = "default"
_NOT_IMPLEMENTED_REASON = "KSM inter-agent bus is not implemented for this client"
_NOT_IMPLEMENTED_NEXT_ACTION = (
    "construct KsmBus/BusClient with a KsmSecretStore and a configured bus record UID."
)
_NOT_IMPLEMENTED_MESSAGE = (
    "KSM inter-agent bus is not implemented for this client. "
    f"next_action: {_NOT_IMPLEMENTED_NEXT_ACTION}"
)


class _KsmBusNotImplementedError(NotImplementedError, CapabilityError):
    """NotImplementedError with legacy CapabilityError compatibility."""

    def __init__(self) -> None:
        NotImplementedError.__init__(self, _NOT_IMPLEMENTED_MESSAGE)
        self.reason = _NOT_IMPLEMENTED_REASON
        self.uid_ref = None
        self.resource_type = None
        self.live_identifier = None
        self.next_action = _NOT_IMPLEMENTED_NEXT_ACTION
        self.context: dict[str, Any] = {}

    def __str__(self) -> str:
        return _NOT_IMPLEMENTED_MESSAGE


def _raise_not_implemented() -> NoReturn:
    raise _KsmBusNotImplementedError()


class VersionConflict(RuntimeError):
    """Raised when a KSM bus compare-and-swap version check fails."""

    def __init__(self, *, key: str, expected_version: int, actual_version: int) -> None:
        self.key = key
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"KSM bus CAS conflict for {key!r}: expected version "
            f"{expected_version}, found {actual_version}"
        )


class BusValue(tuple):
    """Tuple-compatible ``(value, version)`` result with legacy value equality."""

    def __new__(cls, value: Any, version: int) -> BusValue:
        return tuple.__new__(cls, (value, version))

    @property
    def value(self) -> Any:
        return self[0]

    @property
    def version(self) -> int:
        return int(self[1])

    def __eq__(self, other: object) -> bool:
        if isinstance(other, tuple):
            return tuple.__eq__(self, other)
        return self.value == other


def _matching_custom_field(record: Any, key: str) -> dict[str, Any] | None:
    for entry in record.dict.get("custom", []) or []:
        if isinstance(entry, dict) and (entry.get("label") or "") == key:
            return entry
    return None


def _sync_record(record: Any) -> None:
    update = getattr(record, "_update", None)
    if callable(update):
        update()


def _save_record(store: KsmSecretStore, record: Any, *, require_writer: bool) -> None:
    _sync_record(record)
    save = getattr(store.client(), "save", None)
    if callable(save):
        save(record)
        return
    if require_writer:
        raise CapabilityError(
            reason="KSM client does not expose SecretsManager.save(record)",
            next_action=(
                "use keeper-secrets-manager-core with record save support, or mock "
                "save(record) in offline tests; live verification must prove custom-field writes"
            ),
        )


def _validate_key(key: str, *, noun: str = "key") -> None:
    if not isinstance(key, str) or not key:
        raise ValueError(f"KSM bus {noun} must not be empty")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _encode_value(value: Any, version: int) -> str:
    return json.dumps(
        {
            "schema": _BUS_SCHEMA,
            "updated_at": _utc_now(),
            "value": value,
            "version": version,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _decode_value(field: dict[str, Any]) -> BusValue | None:
    values = field.get("value") or []
    if not values:
        return None
    raw = values[0]
    if not isinstance(raw, str):
        return BusValue(raw, 0)
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return BusValue(raw, 0)
    if isinstance(decoded, dict) and decoded.get("schema") == _BUS_SCHEMA:
        return BusValue(decoded.get("value"), int(decoded.get("version") or 0))
    if isinstance(decoded, dict) and "value" in decoded and "version" in decoded:
        return BusValue(decoded.get("value"), int(decoded.get("version") or 0))
    return BusValue(decoded, 0)


def _change_marker(value: Any, version: int) -> str:
    try:
        rendered = json.dumps(value, sort_keys=True, separators=(",", ":"))
    except TypeError:
        rendered = repr(value)
    return f"{version}:{rendered}"


def _channel_name(channel: str | None) -> str:
    name = channel or _DEFAULT_CHANNEL
    _validate_key(name, noun="channel")
    return name


def _channel_key(channel: str | None) -> str:
    return f"{_BUS_CHANNEL_PREFIX}{_channel_name(channel)}"


def _cursor_key(channel: str | None, consumer: str) -> str:
    _validate_key(consumer, noun="consumer")
    return f"{_BUS_CURSOR_PREFIX}{_channel_name(channel)}.{consumer}"


def _message_id(next_version: int) -> str:
    return f"{next_version:020d}-{uuid.uuid4().hex[:12]}"


def _parse_timestamp(value: str) -> datetime | None:
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class BusMessage:
    """Frozen view of one message envelope read from the bus record."""

    id: str
    sender: str
    recipient: str
    subject: str
    timestamp: str
    payload: Any
    trace_id: str | None = None
    ttl_seconds: int = 3600
    channel: str = _DEFAULT_CHANNEL

    def as_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "id": self.id,
            "payload": self.payload,
            "recipient": self.recipient,
            "sender": self.sender,
            "subject": self.subject,
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
            "ttl_seconds": self.ttl_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BusMessage:
        return cls(
            id=str(data.get("id") or ""),
            sender=str(data.get("sender") or ""),
            recipient=str(data.get("recipient") or "*"),
            subject=str(data.get("subject") or ""),
            timestamp=str(data.get("timestamp") or ""),
            payload=data.get("payload"),
            trace_id=data.get("trace_id") if data.get("trace_id") is not None else None,
            ttl_seconds=int(data.get("ttl_seconds") or 3600),
            channel=str(data.get("channel") or _DEFAULT_CHANNEL),
        )

    def expired(self, now: datetime | None = None) -> bool:
        timestamp = _parse_timestamp(self.timestamp)
        if timestamp is None:
            return False
        ttl = timedelta(seconds=self.ttl_seconds)
        return timestamp + ttl <= (now or datetime.now(UTC))


class BusClient:
    """Ordered channel message client backed by :class:`KsmBus`."""

    def __init__(
        self,
        *,
        store: KsmSecretStore,
        directory_uid: str,
        agent_id: str = "agent",
        channel: str = _DEFAULT_CHANNEL,
        max_retries: int = 3,
    ) -> None:
        if not directory_uid or not hasattr(store, "get_record"):
            _raise_not_implemented()
        _validate_key(agent_id, noun="agent_id")
        _validate_key(channel, noun="channel")
        self._bus = KsmBus(store, directory_uid)
        self._agent_id = agent_id
        self._channel = channel
        self._max_retries = max(1, max_retries)

    def _bus_or_raise(self) -> KsmBus:
        bus = getattr(self, "_bus", None)
        if not isinstance(bus, KsmBus):
            _raise_not_implemented()
        return bus

    def _load_channel(self, channel: str | None = None) -> tuple[list[dict[str, Any]], int]:
        entry = self._bus_or_raise().get(_channel_key(channel or self._channel))
        if entry is None:
            return [], 0
        if not isinstance(entry.value, list):
            raise ValueError(
                f"KSM bus channel {_channel_name(channel or self._channel)!r} is corrupt"
            )
        messages = [dict(item) for item in entry.value if isinstance(item, dict)]
        return messages, entry.version

    def publish(
        self,
        *,
        to: str,
        subject: str,
        payload: Any,
        ttl_s: int = 3600,
        trace_id: str | None = None,
        channel: str | None = None,
    ) -> str:
        _validate_key(to, noun="recipient")
        _validate_key(subject, noun="subject")
        bus = self._bus_or_raise()
        selected_channel = _channel_name(channel or self._channel)
        channel_key = _channel_key(selected_channel)
        last_conflict: VersionConflict | None = None
        for _ in range(self._max_retries):
            messages, version = self._load_channel(selected_channel)
            message = BusMessage(
                id=_message_id(version + 1),
                sender=self._agent_id,
                recipient=to,
                subject=subject,
                timestamp=_utc_now(),
                payload=payload,
                trace_id=trace_id,
                ttl_seconds=ttl_s,
                channel=selected_channel,
            )
            try:
                bus.publish(channel_key, [*messages, message.as_dict()], expected_version=version)
                return message.id
            except VersionConflict as exc:
                last_conflict = exc
        if last_conflict is not None:
            raise last_conflict
        raise RuntimeError("KSM bus publish failed without a conflict")

    def subscribe(
        self,
        *,
        since_id: str | None = None,
        consumer: str = "*",
        channel: str | None = None,
    ) -> list[BusMessage]:
        self._bus_or_raise()
        selected_channel = channel or self._channel
        messages, _version = self._load_channel(selected_channel)
        now = datetime.now(UTC)
        out: list[BusMessage] = []
        for raw in messages:
            message = BusMessage.from_dict(raw)
            if since_id is not None and message.id <= since_id:
                continue
            if consumer != "*" and message.recipient not in {consumer, "*"}:
                continue
            if message.expired(now):
                continue
            out.append(message)
        return sorted(out, key=lambda item: item.id)

    def send(
        self,
        *,
        to: str,
        subject: str,
        payload: Any,
        ttl_s: int = 3600,
        trace_id: str | None = None,
        channel: str | None = None,
    ) -> str:
        return self.publish(
            to=to,
            subject=subject,
            payload=payload,
            ttl_s=ttl_s,
            trace_id=trace_id,
            channel=channel,
        )

    def receive(
        self,
        *,
        since_id: str | None = None,
        consumer: str | None = None,
        channel: str | None = None,
    ) -> list[BusMessage]:
        return self.subscribe(
            since_id=since_id,
            consumer=consumer or self._agent_id,
            channel=channel,
        )

    def post(
        self,
        *,
        to: str,
        subject: str,
        payload: Any,
        ttl_s: int = 3600,
        trace_id: str | None = None,
    ) -> str:
        return self.publish(
            to=to,
            subject=subject,
            payload=payload,
            ttl_s=ttl_s,
            trace_id=trace_id,
        )

    def fetch(
        self,
        *,
        since_id: str | None = None,
        consumer: str = "*",
    ) -> list[BusMessage]:
        return self.subscribe(since_id=since_id, consumer=consumer)

    def ack(self, *, last_id: str, consumer: str) -> None:
        _validate_key(last_id, noun="last_id")
        bus = self._bus_or_raise()
        key = _cursor_key(self._channel, consumer)
        current = bus.get(key)
        expected_version = current.version if current is not None else 0
        bus.publish(
            key,
            {"consumer": consumer, "last_id": last_id},
            expected_version=expected_version,
        )

    def gc(self, *, now: datetime | None = None) -> int:
        bus = self._bus_or_raise()
        messages, version = self._load_channel(self._channel)
        kept: list[dict[str, Any]] = []
        removed = 0
        cutoff = now or datetime.now(UTC)
        for raw in messages:
            if BusMessage.from_dict(raw).expired(cutoff):
                removed += 1
            else:
                kept.append(raw)
        if removed:
            bus.publish(_channel_key(self._channel), kept, expected_version=version)
        return removed


class KsmBus:
    """KSM-backed key/value bus using custom fields on one record."""

    def __init__(self, store: KsmSecretStore, record_uid: str) -> None:
        self._store = store
        self._record_uid = record_uid

    def _record(self) -> Any:
        if not self._record_uid:
            _raise_not_implemented()
        return self._store.get_record(self._record_uid)

    def publish(self, key: str, value: Any, expected_version: int | None = None) -> int:
        """Write ``value`` with CAS semantics and return the new version."""
        _validate_key(key)
        record = self._record()
        custom = record.dict.setdefault("custom", [])
        field = _matching_custom_field(record, key)
        current = _decode_value(field) if field is not None else None
        actual_version = current.version if current is not None else 0
        if expected_version is not None and expected_version != actual_version:
            raise VersionConflict(
                key=key,
                expected_version=expected_version,
                actual_version=actual_version,
            )
        next_version = actual_version + 1
        encoded = _encode_value(value, next_version)
        if field is None:
            custom.append({"type": _BUS_FIELD_TYPE, "label": key, "value": [encoded]})
        else:
            field["type"] = _BUS_FIELD_TYPE
            field["value"] = [encoded]
        _save_record(self._store, record, require_writer=True)
        return next_version

    def put(self, key: str, value: str) -> None:
        """Write legacy raw ``value`` to a custom text field labelled ``key``."""
        _validate_key(key)
        record = self._record()
        custom = record.dict.setdefault("custom", [])
        field = _matching_custom_field(record, key)
        if field is None:
            custom.append({"type": _BUS_FIELD_TYPE, "label": key, "value": [value]})
        else:
            field["type"] = _BUS_FIELD_TYPE
            field["value"] = [value]
        _save_record(self._store, record, require_writer=False)

    def get(self, key: str) -> BusValue | None:
        """Read a custom field labelled ``key`` as ``(value, version)``."""
        _validate_key(key)
        field = _matching_custom_field(self._record(), key)
        if field is None:
            return None
        return _decode_value(field)

    def delete(self, key: str) -> None:
        """Remove all custom fields labelled ``key`` from the bus record."""
        _validate_key(key)
        record = self._record()
        custom = record.dict.setdefault("custom", [])
        kept = [
            entry
            for entry in custom
            if not (isinstance(entry, dict) and (entry.get("label") or "") == key)
        ]
        if len(kept) == len(custom):
            return
        record.dict["custom"] = kept
        _save_record(self._store, record, require_writer=True)

    def subscribe(self, key: str, poll_interval: float = 5) -> Iterator[tuple[Any, int]]:
        """Yield ``(value, version)`` whenever ``key`` changes."""
        _validate_key(key)
        if poll_interval < 0:
            raise ValueError("KSM bus poll_interval must not be negative")
        last_marker: str | None = None
        while True:
            current = self.get(key)
            if current is not None:
                marker = _change_marker(current.value, current.version)
                if marker != last_marker:
                    last_marker = marker
                    yield (current.value, current.version)
            time.sleep(poll_interval)


__all__ = ["BusClient", "BusMessage", "BusValue", "KsmBus", "VersionConflict"]
